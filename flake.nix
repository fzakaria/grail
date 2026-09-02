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
          # the CLI, with the multiverse index and clingo baked in;
          # $GRAIL_INDEX still overrides for a local checkout
          grail = pkgs.writeShellApplication {
            name = "grail";
            runtimeInputs = [
              pkgs.python3
              pkgs.clingo
            ];
            text = ''
              export GRAIL_INDEX="''${GRAIL_INDEX:-${multiverse}}"
              export GRAIL_SOLVE_LP="''${GRAIL_SOLVE_LP:-${self}/asp/solve.lp}"
              export PYTHONPATH=${self}
              exec python3 -m grail.cli "$@"
            '';
          };
          default = grail;

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

      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          # the whole Python test suite, clingo included, offline
          tests =
            pkgs.runCommand "grail-tests"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.clingo
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
              pkgs.jq
            ];
            env.GRAIL_INDEX = "${multiverse}";
          };
        }
      );
    };
}
