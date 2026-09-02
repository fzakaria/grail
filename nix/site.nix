# `nix build .#site` — the exact tree the pages workflow deploys and
# `nix run .#serve` tests locally: the site/ files, the repo's solve.lp
# verbatim (the browser runs the same encoding the CLI does), and the data
# shards generated from the multiverse flake input. The footer's
# __STORE_PATH__ placeholder becomes the derivation's own $out, so the
# page names the store path it is served from (a benign self-reference,
# same as the multiverse site).
{
  pkgs,
  self,
  multiverse,
}:
pkgs.runCommand "grail-site" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  mkdir -p $out
  cp -r ${self}/site/. $out/
  chmod -R u+w $out
  # solve.lp rides inside js/ so the content hash below covers it: the
  # solver a page fetches always matches the modules that fetched it
  cp ${self}/asp/solve.lp $out/js/solve.lp
  python3 ${self}/tools/build-site-data.py \
    --index ${multiverse} \
    --out $out/data

  substituteInPlace $out/js/app.js --replace-fail "__STORE_PATH__" "$out"

  # The multiverse cache-busting trick, verbatim: hash the module tree and
  # rename it js.<hash>, so the served HTML and every module (and solve.lp)
  # it pulls in can never be a mismatched pair across deploys. Hashing runs
  # after the substitutions above, so the name covers exactly the bytes
  # served. Modules import each other by relative path, so renaming the
  # directory breaks nothing.
  hash=$(find $out/js -type f | LC_ALL=C sort |
    xargs sha256sum | sha256sum | cut -c1-12)
  mv $out/js "$out/js.$hash"
  substituteInPlace $out/index.html --replace-fail "js/app.js" "js.$hash/app.js"
''
