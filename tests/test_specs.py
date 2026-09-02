# Tests the query grammar in grail.specs: every production of the BNF in
# docs/grammar.md, by parsing query strings and checking both the resulting
# AST shape and which concrete versions each range accepts.
import unittest

from grail.specs import ParseError, parse_query


def accepted(range_, versions):
    """Helper: filter a version list through a parsed range."""
    return [v for v in versions if range_.matches(v)]


class TestGrouping(unittest.TestCase):
    # Whitespace separates independent groups; ^ chains specs into one
    # coexistence group.
    def test_independent_specs(self):
        q = parse_query("python3@>=3.10 ripgrep@14.*")
        self.assertEqual(len(q.groups), 2)
        self.assertEqual(
            [s.attr for g in q.groups for s in g.specs], ["python3", "ripgrep"]
        )

    def test_coexistence_group(self):
        q = parse_query("python3@>=3.10 ^openssl@1.1.*")
        self.assertEqual(len(q.groups), 1)
        self.assertEqual([s.attr for s in q.groups[0].specs], ["python3", "openssl"])

    def test_mixed_groups(self):
        q = parse_query("a@1 ^b@2 c@3")
        self.assertEqual([len(g.specs) for g in q.groups], [2, 1])

    def test_leading_caret_is_an_error(self):
        with self.assertRaises(ParseError):
            parse_query("^a@1")

    def test_bare_attr_matches_everything(self):
        q = parse_query("hello")
        spec = q.groups[0].specs[0]
        self.assertIsNone(spec.range)

    def test_nested_attr(self):
        q = parse_query("jetbrains.idea@2024.*")
        self.assertEqual(q.groups[0].specs[0].attr, "jetbrains.idea")


class TestRanges(unittest.TestCase):
    VERSIONS = ["3.8.9", "3.9.18", "3.10.4", "3.10.12", "3.11.9", "3.12.4"]

    def range_of(self, text):
        return parse_query(f"x@{text}").groups[0].specs[0].range

    # bare version = component-wise prefix, the semantics mvs solve has:
    # 3.10 accepts 3.10.4, refuses 3.1 and 3.100
    def test_bare_prefix(self):
        r = self.range_of("3.10")
        self.assertEqual(accepted(r, self.VERSIONS), ["3.10.4", "3.10.12"])
        self.assertTrue(r.matches("3.10"))
        self.assertFalse(r.matches("3.100"))
        self.assertFalse(r.matches("3.1"))

    # explicit prefix spellings are the same thing
    def test_star_and_x_prefix(self):
        for text in ("3.10.*", "3.10.x"):
            with self.subTest(text=text):
                r = self.range_of(text)
                self.assertEqual(accepted(r, self.VERSIONS), ["3.10.4", "3.10.12"])

    def test_comparators(self):
        r = self.range_of(">=3.10")
        self.assertEqual(
            accepted(r, self.VERSIONS), ["3.10.4", "3.10.12", "3.11.9", "3.12.4"]
        )
        r = self.range_of("<3.10")
        self.assertEqual(accepted(r, self.VERSIONS), ["3.8.9", "3.9.18"])
        r = self.range_of("=3.11.9")
        self.assertEqual(accepted(r, self.VERSIONS), ["3.11.9"])

    # conjunction with , ; both terms must hold
    def test_conjunction(self):
        r = self.range_of(">=3.9,<3.12")
        self.assertEqual(
            accepted(r, self.VERSIONS), ["3.9.18", "3.10.4", "3.10.12", "3.11.9"]
        )

    # alternation with || ; either side may hold
    def test_alternation(self):
        r = self.range_of("3.8.*||3.12.*")
        self.assertEqual(accepted(r, self.VERSIONS), ["3.8.9", "3.12.4"])

    # inclusive interval; the upper endpoint is prefix-inclusive so
    # 3.10..3.11 keeps 3.11.9
    def test_interval(self):
        r = self.range_of("3.10..3.11")
        self.assertEqual(accepted(r, self.VERSIONS), ["3.10.4", "3.10.12", "3.11.9"])

    def test_alternation_binds_looser_than_conjunction(self):
        # (>=3.9 AND <3.10) OR =3.12.4
        r = self.range_of(">=3.9,<3.10||=3.12.4")
        self.assertEqual(accepted(r, self.VERSIONS), ["3.9.18", "3.12.4"])

    def test_malformed(self):
        for bad in ("x@", "x@>=", "x@3..", "x@..3", "@1.0", "x@||", "x y@1 ^", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ParseError):
                    parse_query(bad)


if __name__ == "__main__":
    unittest.main()
