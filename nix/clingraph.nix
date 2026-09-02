# clingraph (and its clorm dependency), neither of which nixpkgs carries.
# Both are pure-Python Potassco projects, so packaging is fetchPypi plus a
# dependency list. clingraph is what renders a plan: a visualization
# encoding in ASP maps solver atoms to graph atoms, graphviz draws them.
{ pkgs }:
let
  python = pkgs.python3;

  clorm = python.pkgs.buildPythonPackage rec {
    pname = "clorm";
    version = "1.6.3";
    pyproject = true;
    src = python.pkgs.fetchPypi {
      inherit pname version;
      hash = "sha256-swYYCQ3WavCQrLyYlrxHXxuoLKc0HpD/yMNUG7cu9JA=";
    };
    build-system = [ python.pkgs.setuptools ];
    dependencies = [ python.pkgs.clingo ];
    # the test suite needs a checkout layout the sdist does not ship
    doCheck = false;
  };
in
python.pkgs.buildPythonApplication rec {
  pname = "clingraph";
  version = "1.2.6";
  pyproject = true;
  src = python.pkgs.fetchPypi {
    inherit pname version;
    hash = "sha256-+75o2PsYvYQ/tGCp6SSWkGWJyqi5Fyw26JxpyRfqeq4=";
  };
  build-system = [
    python.pkgs.setuptools
    python.pkgs.setuptools-scm
  ];
  dependencies = [
    python.pkgs.clingo
    clorm
    python.pkgs.graphviz
    python.pkgs.networkx
    python.pkgs.jsonschema
    python.pkgs.jinja2
  ];
  # graphviz-the-binary is a runtime need of graphviz-the-library
  makeWrapperArgs = [ "--prefix PATH : ${pkgs.graphviz}/bin" ];
  doCheck = false;
}
