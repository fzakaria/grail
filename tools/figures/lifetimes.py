#!/usr/bin/env python3
"""Emit the version-lifetime figure as hand-rolled inline SVG for the blog:
python3 minors and openssl series as life-bars over the full index, with
the coexistence window for `python3@>=3.10 ^openssl@1.1.*` shaded.

No plotting library. The SVG is meant to be INLINED into the page (a
Jekyll include), so text uses the blog's JetBrains Mono and every neutral
color is a var(--token) that follows the site's light/dark palette. The
two series colors are fixed per mode and validated against both papers.

Usage: lifetimes.py --index <multiverse checkout> --out <svg path>
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from grail.index import Index  # noqa: E402
from grail.versions import components, sort_key  # noqa: E402

MONO = '"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace'

# geometry (viewBox units; the page scales the whole thing)
X0, X1 = 64, 748
ROW_H, BAR_H = 17, 7
TOP = 30  # legend row
PANEL_GAP = 30
AXIS_H = 26


def _union(intervals):
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(lo, hi) for lo, hi in merged]


def _series_rows(index, attr, series_of, matches):
    """Aggregate an attr's versions into series -> (runs, matched)."""
    buckets: dict[str, list] = {}
    hit: dict[str, bool] = {}
    for version in index.versions_of(attr):
        series = series_of(version)
        if series is None:
            continue
        buckets.setdefault(series, []).extend(index.runs_of(attr, version))
        hit[series] = hit.get(series, False) or matches(version)
    return {s: (_union(iv), hit[s]) for s, iv in buckets.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    index = Index.load(args.index)
    day = lambda off: date.fromisoformat(index.revision(off).date)

    t0 = date(2012, 7, 1)
    t1 = date(2026, 10, 1)
    x = lambda d: X0 + (d - t0).days / (t1 - t0).days * (X1 - X0)

    py = _series_rows(
        index,
        "python3",
        lambda v: ".".join(components(v)[:2]),
        lambda v: sort_key(v) >= sort_key("3.10"),
    )

    def ssl_series(v):
        c = components(v)
        return "3.x" if c[0] == "3" else ".".join(c[:2]) + ".x"

    ssl = _series_rows(index, "openssl", ssl_series, lambda v: v.startswith("1.1."))

    # the coexistence window: intersect the two constraints' lifetimes
    py_ok = _union(
        r
        for v in index.versions_of("python3")
        if sort_key(v) >= sort_key("3.10")
        for r in index.runs_of("python3", v)
    )
    ssl_ok = _union(
        r
        for v in index.versions_of("openssl")
        if v.startswith("1.1.")
        for r in index.runs_of("openssl", v)
    )
    window = [
        (max(a, c), min(b, d))
        for a, b in py_ok
        for c, d in ssl_ok
        if max(a, c) <= min(b, d)
    ]
    (wlo, whi), *rest = window
    assert not rest, f"expected one window, got {window}"
    wl, wr = day(wlo), day(whi)
    print(f"window: r{wlo}..r{whi}  {wl} .. {wr}")

    # panel layouts: newest series on top
    panels = []
    y = TOP + 18
    for attr, rows in (("python3", py), ("openssl", ssl)):
        order = sorted(rows, key=sort_key, reverse=True)
        panels.append((attr, y, order, rows))
        y += 14 + len(order) * ROW_H + PANEL_GAP
    height = y - PANEL_GAP + AXIS_H
    plot_top, plot_bot = TOP + 8, height - AXIS_H + 4

    svg = []
    put = svg.append
    put(
        f'<svg class="grail-fig" viewBox="0 0 760 {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="version lifetimes of python3 and openssl in '
        f'nixos-unstable with the coexistence window {wl} to {wr} shaded">'
    )
    put(f"""<style>
  .grail-fig {{ font-family: {MONO}; }}
  .grail-fig text {{ font-size: 10px; fill: var(--ink-muted, #565046); }}
  .grail-fig .head {{ font-size: 11px; font-weight: 600; fill: var(--ink, #1a1815); }}
  .grail-fig .grid {{ stroke: var(--rule, #ddd6c9); stroke-width: 1; }}
  .grail-fig .ctx {{ fill: var(--ink-faint, #6f685b); opacity: .55; }}
  .grail-fig .hit {{ fill: #2a78d6; }}
  .grail-fig .win {{ fill: #d8622b; opacity: .16; }}
  .grail-fig .wtext {{ fill: #d8622b; font-size: 10px; }}
  @media (prefers-color-scheme: dark) {{
    .grail-fig .hit {{ fill: #4a90e2; }}
    .grail-fig .win {{ fill: #cf7433; opacity: .2; }}
    .grail-fig .wtext {{ fill: #cf7433; }}
  }}
</style>""")

    # year grid, every two years
    for year in range(2013, 2027, 2):
        gx = x(date(year, 1, 1))
        put(
            f'<line class="grid" x1="{gx:.1f}" y1="{plot_top}" '
            f'x2="{gx:.1f}" y2="{plot_bot}"/>'
        )
        put(
            f'<text x="{gx:.1f}" y="{plot_bot + 16}" '
            f'text-anchor="middle">{year}</text>'
        )

    # the coexistence window, behind the bars
    put(
        f'<rect class="win" x="{x(wl):.1f}" y="{plot_top}" '
        f'width="{max(x(wr) - x(wl), 2):.1f}" height="{plot_bot - plot_top}"/>'
    )
    put(
        f'<text class="wtext" x="{x(wl) - 8:.1f}" y="{plot_top + 12}" '
        f'text-anchor="end">both hold: {wl} → {wr}</text>'
    )

    # legend
    put(f'<rect class="hit" x="{X0}" y="{TOP - 14}" width="18" height="7" rx="3.5"/>')
    put(f'<text x="{X0 + 24}" y="{TOP - 6}">matches the constraint</text>')
    put(
        f'<rect class="ctx" x="{X0 + 210}" y="{TOP - 14}" width="18" height="7" rx="3.5"/>'
    )
    put(f'<text x="{X0 + 234}" y="{TOP - 6}">other versions</text>')

    # panels
    for attr, py0, order, rows in panels:
        put(f'<text class="head" x="4" y="{py0}">{attr}</text>')
        for i, series in enumerate(order):
            cy = py0 + 12 + i * ROW_H
            runs, matched = rows[series]
            put(
                f'<text x="{X0 - 8}" y="{cy + BAR_H - 1}" '
                f'text-anchor="end">{series}</text>'
            )
            cls = "hit" if matched else "ctx"
            for lo, hi in runs:
                bx, bw = x(day(lo)), max(x(day(hi)) - x(day(lo)), BAR_H)
                put(
                    f'<rect class="{cls}" x="{bx:.1f}" y="{cy}" '
                    f'width="{bw:.1f}" height="{BAR_H}" rx="3.5"/>'
                )

    put("</svg>")
    Path(args.out).write_text("\n".join(svg) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
