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
  cp ${self}/asp/solve.lp $out/solve.lp

  chmod -R u+w $out
  python3 ${self}/tools/build-site-data.py \
    --index ${multiverse} \
    --out $out/data

  substituteInPlace $out/js/app.js --replace-fail "__STORE_PATH__" "$out"
''
