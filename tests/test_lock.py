# Tests that grail writes a multiverse.lock byte-compatible with the v1
# format mvs lock writes: {version: 1, pins: {attr: {rev, label, version,
# date}}} where rev is the 12-hex prefix and label is date-rev.
import json
import tempfile
import unittest
from pathlib import Path

from grail.index import Index
from grail.lock import LockError, write_lock
from grail.solve import SolveOptions, solve
from grail.specs import parse_query

FIXTURE = Path(__file__).parent / "fixtures" / "mini-index"


class TestLock(unittest.TestCase):
    def solve(self, query):
        index = Index.load(FIXTURE)
        return solve(parse_query(query), index, SolveOptions())

    def test_v1_format(self):
        plan = self.solve("foo@1.1 ^bar@1.0")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "multiverse.lock"
            write_lock(plan, path)
            lock = json.loads(path.read_text())

        self.assertEqual(lock["version"], 1)
        self.assertEqual(set(lock["pins"]), {"foo", "bar"})
        pin = lock["pins"]["foo"]
        # the winning revision is offset 11: 2020-12-01, rev 11*20
        self.assertEqual(pin["rev"], "1" * 12)
        self.assertEqual(pin["date"], "2020-12-01")
        self.assertEqual(pin["label"], "2020-12-01-" + "1" * 12)
        self.assertEqual(pin["version"], "1.1")

    def test_unsat_refuses(self):
        plan = self.solve("foo@1.0 ^bar@1.1")
        with self.assertRaises(LockError):
            write_lock(plan, Path("/dev/null"))

    def test_duplicate_attr_refuses(self):
        plan = self.solve("foo@1.0 foo@2.0")
        with self.assertRaises(LockError):
            write_lock(plan, Path("/dev/null"))


if __name__ == "__main__":
    unittest.main()
