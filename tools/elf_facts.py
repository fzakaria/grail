#!/usr/bin/env python3
"""Tier-1 fact extraction: read one ELF and emit its link-time demands as
ASP facts. Stdlib only, 64-bit little-endian ELF only (the multiverse's
x86_64/aarch64 targets), because the point is the demand side:

    needs(P, "libc.so.6").          DT_NEEDED sonames
    verneed(P, "libc.so.6", "GLIBC_2.27").   .gnu.version_r demands
    runpath(P, "/nix/store/...").   where a second glibc would sneak from
    interp(P, "/nix/store/.../ld-linux-x86-64.so.2").

Usage: elf_facts.py <path> [<fact id>]
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

_MAGIC = b"\x7fELF"
_CLASS64 = 2
_DATA_LE = 1

# section types
_SHT_DYNAMIC = 6
_SHT_GNU_VERNEED = 0x6FFFFFFE

# dynamic tags
_DT_NEEDED = 1
_DT_RPATH = 15
_DT_RUNPATH = 29

# program header types
_PT_INTERP = 3


class NotAnElf(ValueError):
    pass


@dataclass
class ElfFacts:
    needed: list[str] = field(default_factory=list)
    # soname -> set of demanded version names, e.g. {"GLIBC_2.17", ...}
    verneed: dict[str, set[str]] = field(default_factory=dict)
    runpath: list[str] = field(default_factory=list)
    interp: str | None = None

    def to_asp(self, ident: str) -> str:
        lines = []
        for soname in self.needed:
            lines.append(f'needs("{ident}", "{soname}").')
        for soname, versions in sorted(self.verneed.items()):
            for version in sorted(versions):
                lines.append(f'verneed("{ident}", "{soname}", "{version}").')
        for path in self.runpath:
            lines.append(f'runpath("{ident}", "{path}").')
        if self.interp:
            lines.append(f'interp("{ident}", "{self.interp}").')
        return "\n".join(lines) + "\n"

    def max_glibc(self) -> str | None:
        """The largest GLIBC_x.y demand, the one-number compatibility bound."""
        demands = {
            v
            for versions in self.verneed.values()
            for v in versions
            if v.startswith("GLIBC_") and v != "GLIBC_PRIVATE"
        }
        if not demands:
            return None
        return max(
            demands, key=lambda v: [int(p) for p in v[len("GLIBC_") :].split(".")]
        )


def _cstr(blob: bytes, offset: int) -> str:
    end = blob.index(b"\x00", offset)
    return blob[offset:end].decode("utf-8", "replace")


def extract(path: str | Path) -> ElfFacts:
    data = Path(path).read_bytes()
    if data[:4] != _MAGIC:
        raise NotAnElf(f"{path} is not an ELF file")
    if data[4] != _CLASS64 or data[5] != _DATA_LE:
        raise NotAnElf(f"{path}: only 64-bit little-endian ELF is supported")

    facts = ElfFacts()

    # ELF header fields we need
    (e_phoff,) = struct.unpack_from("<Q", data, 0x20)
    (e_shoff,) = struct.unpack_from("<Q", data, 0x28)
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 0x36)
    e_shentsize, e_shnum = struct.unpack_from("<HH", data, 0x3A)

    # PT_INTERP from the program headers
    for i in range(e_phnum):
        base = e_phoff + i * e_phentsize
        (p_type,) = struct.unpack_from("<I", data, base)
        if p_type != _PT_INTERP:
            continue
        (p_offset,) = struct.unpack_from("<Q", data, base + 8)
        facts.interp = _cstr(data, p_offset)

    # section headers: (type, offset, size, link) per section
    sections = []
    for i in range(e_shnum):
        base = e_shoff + i * e_shentsize
        sh_type = struct.unpack_from("<I", data, base + 4)[0]
        sh_offset = struct.unpack_from("<Q", data, base + 24)[0]
        sh_size = struct.unpack_from("<Q", data, base + 32)[0]
        sh_link = struct.unpack_from("<I", data, base + 40)[0]
        sections.append((sh_type, sh_offset, sh_size, sh_link))

    def strtab_of(section) -> bytes:
        _, off, size, _ = sections[section[3]]
        return data[off : off + size]

    for section in sections:
        sh_type, sh_offset, sh_size, _ = section

        # DT_NEEDED and DT_RUNPATH out of the dynamic section
        if sh_type == _SHT_DYNAMIC:
            strings = strtab_of(section)
            for off in range(sh_offset, sh_offset + sh_size, 16):
                d_tag, d_val = struct.unpack_from("<qQ", data, off)
                if d_tag == 0:
                    break
                if d_tag == _DT_NEEDED:
                    facts.needed.append(_cstr(strings, d_val))
                elif d_tag in (_DT_RUNPATH, _DT_RPATH):
                    facts.runpath.extend(_cstr(strings, d_val).split(":"))

        # version demands out of .gnu.version_r
        if sh_type == _SHT_GNU_VERNEED:
            strings = strtab_of(section)
            off = sh_offset
            while True:
                _, vn_cnt, vn_file, vn_aux, vn_next = struct.unpack_from(
                    "<HHIII", data, off
                )
                soname = _cstr(strings, vn_file)
                demands = facts.verneed.setdefault(soname, set())

                aux = off + vn_aux
                for _ in range(vn_cnt):
                    _, _, _, vna_name, vna_next = struct.unpack_from(
                        "<IHHII", data, aux
                    )
                    demands.add(_cstr(strings, vna_name))
                    if vna_next == 0:
                        break
                    aux += vna_next

                if vn_next == 0:
                    break
                off += vn_next

    return facts


def main() -> int:
    if len(sys.argv) < 2:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    path = sys.argv[1]
    ident = sys.argv[2] if len(sys.argv) > 2 else Path(path).name

    facts = extract(path)
    sys.stdout.write(facts.to_asp(ident))

    bound = facts.max_glibc()
    if bound:
        print(f"% max glibc demand: {bound}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
