#!/usr/bin/env python3
"""Touch up a graphviz SVG for the blog: widen the font-family attributes
graphviz writes ("JetBrains Mono") into a full monospace fallback stack.
Colors and intrinsic width/height stay exactly as graphviz baked them —
the blog serves figures as ordinary images on its light --image-mat in
both color schemes, so the palette is literal light line art on
transparent, validated against the mat color.

Usage: tokenize_svg.py <in.svg> <out.svg>
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"

MONO = '"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace'


def main(src: str, dst: str) -> None:
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(src)
    root = tree.getroot()
    root.set("class", "grail-fig")

    for el in root.iter():
        if "font-family" in el.attrib:
            el.set("font-family", MONO)

    with open(dst, "w") as f:
        f.write(ET.tostring(root, encoding="unicode") + "\n")
    print(f"wrote {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
