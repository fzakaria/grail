#!/usr/bin/env python3
"""Rewrite a graphviz SVG for inlining into the blog: strip the fixed
width/height (the viewBox scales it to the column), move every fill/stroke
presentation attribute into a style attribute, and map graphviz's baked
colors onto the site's CSS custom properties so the diagram follows the
light/dark palette. Presentation attributes cannot hold var(), which is
the whole reason this pass exists.

Usage: tokenize_svg.py <in.svg> <out.svg>
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"

# graphviz color -> site token (with the light value as fallback)
COLOR_MAP = {
    "#fcfcfb": "var(--paper-raised, #ebe6da)",  # node fill
    "#b5b1a9": "var(--rule-strong, #c2b9a6)",  # node border
    "#0b0b0b": "var(--ink, #1a1815)",  # node text
    "#52514e": "var(--ink-muted, #565046)",  # edge labels
    "#7d7970": "var(--ink-faint, #6f685b)",  # edges + arrowheads
    "#2a78d6": "var(--grail-blue, #2a78d6)",  # the clingo node
    "#fdeee6": "var(--accent-wash, #9e34131f)",  # the plan node fill
    "#d8622b": "var(--accent, #9e3413)",  # the plan node border
}

# the dark half of the two series colors; everything else is a site token
DARK_OVERRIDES = (
    "@media (prefers-color-scheme: dark) {" " .grail-pipe { --grail-blue: #4a90e2; } }"
)

MONO = '"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace'


def main(src: str, dst: str) -> None:
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(src)
    root = tree.getroot()

    # the viewBox already carries the aspect ratio; fixed pt sizes fight
    # the page column
    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    root.set("class", "grail-pipe")

    for el in root.iter():
        styles = []
        for attr in ("fill", "stroke"):
            value = el.attrib.pop(attr, None)
            if value is None:
                continue
            styles.append(f"{attr}:{COLOR_MAP.get(value.lower(), value)}")
        if "font-family" in el.attrib:
            el.attrib.pop("font-family")
            styles.append(f"font-family:{MONO}")
        if styles:
            existing = el.attrib.get("style", "")
            el.set("style", ";".join(filter(None, [existing, *styles])))

    style = ET.SubElement(root, f"{{{SVG_NS}}}style")
    style.text = DARK_OVERRIDES
    # graphviz draws a background polygon in the graph color; with
    # bgcolor=transparent it emits none, but strip any pure-white one that
    # slips through an older graphviz
    out = ET.tostring(root, encoding="unicode")
    out = re.sub(r'<polygon[^>]*style="fill:white[^"]*"[^>]*/>', "", out, count=1)
    with open(dst, "w") as f:
        f.write(out + "\n")
    print(f"wrote {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
