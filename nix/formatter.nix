# `nix fmt`. The tree wrapper, matching nixpkgs-multiverse: one formatting
# step covers every language in the tree. black for the Python (the solver
# driver, the tests, the tools), prettier for markdown at the width the
# docs are written to. The .lp files have no formatter; clingo's grammar is
# its own discipline.
{ pkgs }:
pkgs.nixfmt-tree.override {
  runtimeInputs = [
    pkgs.black
    pkgs.prettier
  ];
  settings = {
    formatter.black = {
      command = "black";
      options = [ "--quiet" ];
      includes = [ "*.py" ];
    };
    # proseWrap stays at its default of preserving the author's line
    # breaks: these files are hand-wrapped prose, and reflowing would make
    # every future diff a whole-file diff.
    formatter.prettier-markdown = {
      command = "prettier";
      options = [
        "--write"
        "--print-width"
        "80"
      ];
      includes = [ "*.md" ];
    };
  };
}
