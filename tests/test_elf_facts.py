# Tests the tier-1 fact extractor by parsing the running Python
# interpreter's own ELF binary: any dynamically linked python needs
# libc.so.6 and demands at least one GLIBC_* symbol version from it.
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import elf_facts  # noqa: E402


def _elf_target():
    exe = Path(sys.executable).resolve()
    try:
        if exe.read_bytes()[:4] == b"\x7fELF":
            return exe
    except OSError:
        pass
    return None


class TestElfFacts(unittest.TestCase):
    @unittest.skipUnless(_elf_target(), "no ELF python to parse")
    def test_python_binary(self):
        facts = elf_facts.extract(_elf_target())

        self.assertTrue(any(n.startswith("libc.so") for n in facts.needed))
        glibc_demands = facts.verneed.get("libc.so.6", set())
        self.assertTrue(any(v.startswith("GLIBC_") for v in glibc_demands))
        # the loader is recorded, and on NixOS it pins a specific glibc
        self.assertTrue(facts.interp)

    @unittest.skipUnless(_elf_target(), "no ELF python to parse")
    def test_asp_rendering(self):
        facts = elf_facts.extract(_elf_target())
        text = facts.to_asp("me")
        self.assertIn('needs("me", "libc.so', text)
        self.assertIn("verneed(", text)

    def test_not_an_elf(self):
        with self.assertRaises(elf_facts.NotAnElf):
            elf_facts.extract(Path(__file__))


if __name__ == "__main__":
    unittest.main()
