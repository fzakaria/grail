# Golden tests for the clingo solve pipeline against the hand-written
# mini-index (20 revisions, a hole in foo 1.1 at rev 9, an open tip, and a
# glibc era change at rev 10). Each test states the expected optimum and
# why it is optimal under the objective stack: fewest revisions, then
# newest versions, then fewest glibc eras, then freshest builds.
import unittest
from pathlib import Path

from grail.index import Index
from grail.solve import SolveOptions, solve
from grail.specs import parse_query

FIXTURE = Path(__file__).parent / "fixtures" / "mini-index"


def run(query, **kwargs):
    index = Index.load(FIXTURE)
    return solve(parse_query(query), index, SolveOptions(**kwargs))


class TestCoexistence(unittest.TestCase):
    # foo 1.1 lives {5..8, 10..11}, bar 1.0 lives {7..14}; the overlap is
    # {7, 8, 10, 11} and freshest-build picks 11.
    def test_overlap_found(self):
        plan = run("foo@1.1 ^bar@1.0")
        self.assertEqual(plan.result, "sat")
        self.assertEqual(plan.revisions, 1)
        self.assertEqual(plan.groups[0].revision.off, 11)
        self.assertEqual(
            {(p.attr, p.version) for p in plan.groups[0].pins},
            {("foo", "1.1"), ("bar", "1.0")},
        )

    # foo 1.0 dies at rev 4, bar 1.1 is born at rev 15: no shared moment
    # ever existed, and the explanation names the gap.
    def test_never_overlapped(self):
        plan = run("foo@1.0 ^bar@1.1")
        self.assertEqual(plan.result, "unsat")
        self.assertIn("never", plan.why)
        self.assertIn("foo", plan.why)
        self.assertIn("bar", plan.why)
        self.assertIn("2020-05-01", plan.why)  # last day foo 1.0 was alive
        self.assertIn("2021-04-01", plan.why)  # first day bar 1.1 existed

    # ranges: >=1.1 lets the solver take foo 2.0 with bar 1.1 at one shared
    # revision; newest-versions beats settling for foo 1.1 + bar 1.0.
    def test_range_prefers_newer_versions(self):
        plan = run("foo@>=1.1 ^bar")
        self.assertEqual(plan.revisions, 1)
        self.assertEqual(plan.groups[0].revision.off, 19)
        self.assertEqual(
            {(p.attr, p.version) for p in plan.groups[0].pins},
            {("foo", "2.0"), ("bar", "1.1")},
        )


class TestIndependentGroups(unittest.TestCase):
    # Two independent specs that can share a revision must share one.
    def test_groups_merge_onto_one_revision(self):
        plan = run("foo@>=1.1 bar")
        self.assertEqual(plan.revisions, 1)

    # foo 1.1 and bar 1.1 never overlap, so two revisions are needed; the
    # one-glibc constraint then forces foo onto its 2.31-era run {10, 11}
    # and freshest-build picks 11 for foo and 19 for bar.
    def test_one_glibc_picks_the_hole_side_run(self):
        plan = run("foo@1.1 bar@1.1", one_glibc=True)
        self.assertEqual(plan.result, "sat")
        self.assertEqual(plan.revisions, 2)
        offs = sorted(g.revision.off for g in plan.groups)
        self.assertEqual(offs, [11, 19])
        self.assertEqual(plan.glibcs, ["2.31"])

    # foo 1.0 exists only under glibc 2.30 and bar 1.1 only under 2.31, so
    # demanding one glibc is impossible and the explanation says so.
    def test_one_glibc_unsat(self):
        plan = run("foo@1.0 bar@1.1", one_glibc=True)
        self.assertEqual(plan.result, "unsat")
        self.assertIn("glibc", plan.why)


class TestClamps(unittest.TestCase):
    # --before drops every revision after the date; bar's best version
    # inside the clamp is 1.0 (born rev 7) and freshest is rev 8.
    def test_before(self):
        plan = run("bar", before="2020-09-15")
        self.assertEqual(plan.groups[0].pins[0].version, "1.0")
        self.assertEqual(plan.groups[0].revision.off, 8)

    def test_after_kills_dead_package(self):
        # baz died at rev 3 (2020-04); after 2021 there is nothing left
        plan = run("baz", after="2021-01-01")
        self.assertEqual(plan.result, "unsat")


class TestErrors(unittest.TestCase):
    def test_no_matching_version(self):
        plan = run("baz@4.*")
        self.assertEqual(plan.result, "unsat")
        self.assertIn("baz", plan.why)

    def test_unknown_attr(self):
        plan = run("nosuchpackage")
        self.assertEqual(plan.result, "unsat")
        self.assertIn("nosuchpackage", plan.why)


if __name__ == "__main__":
    unittest.main()
