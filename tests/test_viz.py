# Tests the clingraph rendering path against the mini-index: fact
# emission is checked always; the actual render runs only when a
# clingraph binary is reachable (the flake's checks provide one).
import shutil
import tempfile
import unittest
from pathlib import Path

from grail.index import Index
from grail.solve import SolveOptions, solve
from grail.specs import parse_query
from grail.viz import VizError, plan_facts, render

FIXTURE = Path(__file__).parent / "fixtures" / "mini-index"

import os

_CLINGRAPH = shutil.which(os.environ.get("GRAIL_CLINGRAPH", "clingraph"))


class TestVizFacts(unittest.TestCase):
    def setUp(self):
        self.index = Index.load(FIXTURE)

    def plan(self, query):
        return solve(parse_query(query), self.index, SolveOptions())

    # foo@1.1 ^bar@1.0 solves to revision 11, glibc era 2.31
    def test_facts(self):
        facts = plan_facts(self.plan("foo@1.1 ^bar@1.0"), self.index)
        self.assertIn('revnode(g0, "r11 · 2020-12-01\\nglibc 2.31").', facts)
        self.assertIn('pinnode(p0, g0, "foo 1.1").', facts)
        self.assertIn('pinnode(p1, g0, "bar 1.0").', facts)

    def test_unsat_refuses(self):
        with self.assertRaises(VizError):
            plan_facts(self.plan("foo@1.0 ^bar@1.1"), self.index)


class TestVizRender(unittest.TestCase):
    @unittest.skipUnless(_CLINGRAPH, "no clingraph binary")
    def test_render_dot_and_svg(self):
        index = Index.load(FIXTURE)
        plan = solve(parse_query("foo@1.1 ^bar@1.0"), index, SolveOptions())
        with tempfile.TemporaryDirectory() as tmp:
            dot = Path(tmp) / "plan.dot"
            render(plan, index, dot)
            text = dot.read_text()
            self.assertIn("foo 1.1", text)
            self.assertIn("r11", text)

            svg = Path(tmp) / "plan.svg"
            render(plan, index, svg)
            self.assertIn(b"<svg", svg.read_bytes())


if __name__ == "__main__":
    unittest.main()
