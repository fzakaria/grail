# Tests grail.versions.compare against the documented behavior of Nix's
# builtins.compareVersions, using a table of pairs whose expected ordering
# was checked against `nix eval` (see the parity comment on each row).
import unittest

from grail.versions import compare, components


class TestComponents(unittest.TestCase):
    # Splitting mirrors Nix's nextComponent: runs of digits or runs of
    # non-digits, with '.' and '-' acting as separators that vanish.
    def test_split(self):
        self.assertEqual(components("3.10.2"), ["3", "10", "2"])
        self.assertEqual(components("2.3pre1"), ["2", "3", "pre", "1"])
        self.assertEqual(components("1.0-rc4"), ["1", "0", "rc", "4"])
        self.assertEqual(components(""), [])


class TestCompare(unittest.TestCase):
    # Each row: (a, b, sign of compareVersions a b).
    TABLE = [
        ("1.0", "1.0", 0),  # equal
        ("1.0", "2.0", -1),  # numeric
        ("2.3", "2.10", -1),  # numeric, not lexicographic
        ("2.3", "2.3.0", -1),  # missing component is smaller
        ("2.3pre1", "2.3", -1),  # pre sorts before the release
        ("2.3pre4", "2.3.4", -1),  # pre sorts before anything released
        ("2.3a", "2.3.1", -1),  # letters sort below numbers
        ("2.3.1", "2.3.1a", -1),  # empty sorts below a letter: only pre is special
        ("8.0a", "8.0b", -1),  # letters compare lexically
        ("3.10", "3.9", 1),  # the reason string compare is wrong
        ("", "1", -1),  # empty is smaller than anything numeric
        ("1.0-rc1", "1.0", 1),  # rc is NOT special; only pre sorts early
    ]

    def test_table(self):
        for a, b, sign in self.TABLE:
            with self.subTest(a=a, b=b):
                got = compare(a, b)
                norm = (got > 0) - (got < 0)
                self.assertEqual(norm, sign)
                # antisymmetry, for free
                got_rev = compare(b, a)
                self.assertEqual((got_rev > 0) - (got_rev < 0), -sign)


if __name__ == "__main__":
    unittest.main()
