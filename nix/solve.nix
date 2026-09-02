# The IFD solve: the resolver is itself a derivation. It reads the index
# out of the multiverse flake input, runs clingo in the sandbox, and the
# plan comes back into eval via fromJSON. An unsatisfiable query fails the
# derivation, so the solver's explanation is the build error.
{
  pkgs,
  self,
  multiverse,
}:
{
  specs,
  oneGlibc ? false,
  before ? null,
  after ? null,
  name ? "grail-plan",
}:
let
  inherit (pkgs) lib;

  args =
    [
      "solve"
      "--json"
    ]
    ++ lib.optional oneGlibc "--one-glibc"
    ++ lib.optionals (before != null) [
      "--before"
      before
    ]
    ++ lib.optionals (after != null) [
      "--after"
      after
    ]
    ++ [ specs ];

  drv =
    pkgs.runCommand "${name}.json"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.clingo
        ];
      }
      ''
        export GRAIL_INDEX=${multiverse}
        export GRAIL_SOLVE_LP=${self}/asp/solve.lp
        export PYTHONPATH=${self}
        python3 -m grail.cli ${lib.escapeShellArgs args} > $out
      '';
in
builtins.fromJSON (builtins.readFile drv)
