# mkDerivation with version ranges. The solver picks versions and
# revisions; multiverse's `at` materialises each chosen revision; solved
# attrs land in buildInputs. The stdenv comes from the newest revision the
# plan uses, so in a single-group (coexistence) plan the compiler, glibc
# and every input are one time-consistent world.
{
  lib,
  mv, # multiverse.multiverse.${system}
  solve, # the IFD solve from solve.nix
}:
{
  specs,
  oneGlibc ? false,
  one ? [ ],
  before ? null,
  after ? null,
  ...
}@args:
let
  plan = solve {
    inherit
      specs
      oneGlibc
      one
      before
      after
      ;
  };

  # walk a nested-set attr path like "jetbrains.idea"
  resolvePin = pkgs: pin: lib.attrsets.getAttrFromPath (lib.splitString "." pin.attr) pkgs;

  # one materialised nixpkgs per revision the plan chose
  materialised = map (g: {
    pkgs = mv.at g.revision.label;
    inherit (g) pins;
  }) plan.groups;

  solvedInputs = lib.concatMap (g: map (resolvePin g.pkgs) g.pins) materialised;

  # plan.groups arrive sorted by revision offset, so the last group is the
  # newest world; its stdenv links everything
  buildWorld = (lib.last materialised).pkgs;

  # everything mkDerivation should not see
  solverArgs = [
    "specs"
    "oneGlibc"
    "one"
    "before"
    "after"
  ];
in
buildWorld.stdenv.mkDerivation (
  builtins.removeAttrs args solverArgs
  // {
    buildInputs = (args.buildInputs or [ ]) ++ solvedInputs;
    passthru = (args.passthru or { }) // {
      grailPlan = plan;
    };
  }
)
