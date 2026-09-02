{
  description = "Version-range concretization over nixpkgs-multiverse, solved by clingo";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    multiverse.url = "github:fzakaria/nixpkgs-multiverse";
  };

  outputs =
    {
      self,
      nixpkgs,
      multiverse,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        rec {
          # nixpkgs has neither clingraph nor its clorm dependency
          clingraph = import ./nix/clingraph.nix { inherit pkgs; };

          # the CLI, with the multiverse index, clingo and clingraph baked
          # in; $GRAIL_INDEX still overrides for a local checkout
          grail = pkgs.writeShellApplication {
            name = "grail";
            runtimeInputs = [
              pkgs.python3
              pkgs.clingo
              clingraph
            ];
            text = ''
              export GRAIL_INDEX="''${GRAIL_INDEX:-${multiverse}}"
              export GRAIL_SOLVE_LP="''${GRAIL_SOLVE_LP:-${self}/asp/solve.lp}"
              export PYTHONPATH=${self}
              exec python3 -m grail.cli "$@"
            '';
          };
          default = grail;

          # the browser solver: site/ + solve.lp + data shards from the
          # multiverse input — the tree the pages workflow deploys
          site = import ./nix/site.nix {
            inherit pkgs self;
            inherit multiverse;
          };

          # the party trick: a derivation whose inputs the solver chose.
          # python >= 3.10 and openssl 1.1 last coexisted on 2022-09-12
          # (r852); stdenv, glibc and both inputs come from that world.
          demo = self.lib.${system}.mkDerivation {
            pname = "grail-demo";
            version = "0.1";
            specs = "python3@>=3.10 ^openssl@1.1.*";
            dontUnpack = true;
            installPhase = ''
              {
                python3 --version
                openssl version
                echo "glibc $(ldd --version | head -1)"
              } | tee $out
            '';
          };
        }
      );

      lib = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          solve = import ./nix/solve.nix {
            inherit pkgs self;
            inherit multiverse;
          };
        in
        {
          # solve a query at eval time (IFD); returns the plan as a value
          inherit solve;

          # mkDerivation with version ranges
          mkDerivation = import ./nix/mkDerivation.nix {
            inherit (pkgs) lib;
            mv = multiverse.multiverse.${system};
            inherit solve;
          };
        }
      );

      apps = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          # serve the built site locally, exactly the tree pages deploys
          serve = {
            type = "app";
            program = "${pkgs.writeShellScript "serve-site" ''
              exec ${pkgs.python3}/bin/python3 -m http.server 8137 \
                --directory ${self.packages.${system}.site}
            ''}";
          };
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          # the site assembles, and the JS compareVersions port agrees with
          # the Python one (which test_versions.py holds against real nix)
          site =
            pkgs.runCommand "grail-site-check"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.nodejs
                ];
              }
              ''
                test -f ${self.packages.${system}.site}/index.html
                test -f ${self.packages.${system}.site}/solve.lp
                test -f ${self.packages.${system}.site}/data/attrs.json

                python3 - <<'EOF' > expected.json
                import json, sys
                sys.path.insert(0, "${self}")
                from grail.versions import compare
                pairs = json.load(open("${self}/tests/fixtures/version-pairs.json"))
                sign = lambda n: (n > 0) - (n < 0)
                json.dump([sign(compare(a, b)) for a, b in pairs], sys.stdout)
                EOF
                node ${self}/tests/site/versions-parity.mjs \
                  ${self}/tests/fixtures/version-pairs.json \
                  expected.json \
                  ${self}/site/js/versions.js
                touch $out
              '';

          # the whole Python test suite, clingo and clingraph included,
          # offline
          tests =
            pkgs.runCommand "grail-tests"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.clingo
                  self.packages.${system}.clingraph
                ];
              }
              ''
                cd ${self}
                python3 -m unittest discover -s tests -v
                touch $out
              '';

          # the IFD path end to end against the offline mini-index: the plan
          # for foo@1.1 ^bar@1.0 must land on fixture revision 11
          ifd =
            let
              solveFixture = import ./nix/solve.nix {
                inherit pkgs self;
                multiverse = ./tests/fixtures/mini-index;
              };
              plan = solveFixture { specs = "foo@1.1 ^bar@1.0"; };
            in
            assert plan.result == "sat";
            assert plan.revisions == 1;
            assert (builtins.head plan.groups).revision.off == 11;
            pkgs.runCommand "grail-ifd-ok" { } "touch $out";
        }
      );

      formatter = forAllSystems (
        system:
        import ./nix/formatter.nix {
          pkgs = nixpkgs.legacyPackages.${system};
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python3
              pkgs.clingo
              self.packages.${system}.clingraph
              pkgs.jq
            ];
            env.GRAIL_INDEX = "${multiverse}";
          };
        }
      );
    };
}
