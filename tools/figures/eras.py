#!/usr/bin/env python3
"""Emit the era-retreat figure as hand-rolled inline SVG for the blog:
the lifetimes of postgresql 13.x and python3 3.10.x over 2022-2024, the
glibc/zstd/openssl eras beneath them, and the window where every era
agrees — the strip `--one zstd --one openssl` forces the plan into,
retreating python from 3.10.12 (r1128) to 3.10.4 (r793).

No plotting library, same conventions as lifetimes.py: light line art on
transparent, served as an ordinary /assets image in both color schemes.

Usage: eras.py --index <multiverse checkout> --out <svg path>
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from grail.index import Index  # noqa: E402

MONO = '"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace'

# geometry (viewBox units; the page scales the whole thing)
X0, X1 = 92, 592
ROW_H, BAR_H = 26, 9
ERA_H = 17
TOP = 34  # legend row

# the story's cast, all pulled from the index at run time
LIBS = ("glibc", "zstd", "openssl")
FREE_OFF, COHERENT_OFF, POSTGRES_OFF = 1128, 793, 771

# label an era segment inline only when it can hold its version text
MIN_LABEL_W = 50


def _union(intervals):
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(lo, hi) for lo, hi in merged]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    index = Index.load(args.index)
    day = lambda off: date.fromisoformat(index.revision(off).date)

    t0 = date(2022, 1, 1)
    t1 = date(2024, 1, 1)
    x = lambda d: X0 + (d - t0).days / (t1 - t0).days * (X1 - X0)
    clamp = lambda d: min(max(d, t0), t1)

    # the two requested attrs, as merged series lifetimes
    attrs = []
    for attr, want in (
        ("postgresql", lambda v: v.startswith("13.")),
        ("python3", lambda v: v.startswith("3.10.")),
    ):
        runs = _union(
            r
            for v in index.versions_of(attr)
            if want(v)
            for r in index.runs_of(attr, v)
        )
        attrs.append((attr, runs))

    # the era each --one lib holds at the coherent plan, and its bounds:
    # their intersection is the window every constrained plan must fit
    wlo, whi = 0, index.tip
    binding = {}
    for lib in LIBS:
        for version, lo, hi in index.eras_of(lib):
            if lo <= COHERENT_OFF <= hi:
                binding[lib] = version
                wlo, whi = max(wlo, lo), min(whi, hi)
    wl, wr = day(wlo), day(whi)
    print(f"window: r{wlo}..r{whi}  {wl} .. {wr}  ({binding})")
    assert whi == COHERENT_OFF, "expected the window to end at the python pin"

    # layout: legend, two attr rows, three era strips, axis
    y_attr = TOP + 44
    y_era = y_attr + len(attrs) * ROW_H + 46
    plot_top = TOP + 34
    plot_bot = y_era + len(LIBS) * ROW_H - (ROW_H - ERA_H) + 6
    height = plot_bot + 30

    svg = []
    put = svg.append
    put(
        f'<svg class="grail-fig" viewBox="0 0 600 {height}" '
        f'width="600" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="postgresql 13 and python 3.10 lifetimes over the '
        f"glibc, zstd and openssl eras; the window where every era "
        f'agrees ends {wr}, where the coherent plan pins python 3.10.4">'
    )
    put(f"""<style>
  .grail-fig {{ font-family: {MONO}; }}
  .grail-fig text {{ font-size: 12px; fill: #565046; }}
  .grail-fig .head {{ font-size: 13px; font-weight: 600; fill: #1a1815; }}
  .grail-fig .grid {{ stroke: #dcd5c5; stroke-width: 1; }}
  .grail-fig .hit {{ fill: #2a78d6; }}
  .grail-fig .era {{ fill: #6f685b; opacity: .35; }}
  .grail-fig .era.odd {{ opacity: .55; }}
  .grail-fig .etext {{ fill: #3f3a31; font-size: 11px; }}
  .grail-fig .win {{ fill: #cf5d28; opacity: .16; }}
  .grail-fig .wtext {{ fill: #cf5d28; font-size: 12px; }}
  .grail-fig .pin {{ fill: #cf5d28; stroke: #f6f1e5; stroke-width: 1.5; }}
  .grail-fig .free {{ fill: none; stroke: #6f685b; stroke-width: 2; }}
  .grail-fig .arrow {{ stroke: #cf5d28; stroke-width: 1.4; fill: none; }}
</style>""")

    # half-year grid
    for year in (2022, 2023, 2024):
        for month in (1, 7):
            d = date(year, month, 1)
            if not t0 <= d <= t1:
                continue
            gx = x(d)
            put(
                f'<line class="grid" x1="{gx:.1f}" y1="{plot_top}" '
                f'x2="{gx:.1f}" y2="{plot_bot}"/>'
            )
            anchor = "end" if gx > X1 - 20 else "middle"
            put(
                f'<text x="{gx:.1f}" y="{plot_bot + 16}" '
                f'text-anchor="{anchor}">{d.strftime("%Y-%m")}</text>'
            )

    # the agreement window, behind everything
    put(
        f'<rect class="win" x="{x(wl):.1f}" y="{plot_top}" '
        f'width="{max(x(wr) - x(wl), 2):.1f}" height="{plot_bot - plot_top}"/>'
    )
    put(
        f'<text class="wtext" x="{x(wr) + 8:.1f}" y="{y_era - 26}">'
        f"every era agrees: {wl} → {wr}</text>"
    )
    put(
        f'<text class="wtext" x="{x(wr) + 8:.1f}" y="{y_era - 10}">'
        f"(openssl 1.1.1o is the wall)</text>"
    )

    # legend
    put(f'<rect class="hit" x="{X0}" y="{TOP - 14}" width="18" height="7" rx="3.5"/>')
    put(f'<text x="{X0 + 24}" y="{TOP - 6}">requested attr lifetime</text>')
    put(f'<rect class="era odd" x="{X0 + 250}" y="{TOP - 16}" width="18" height="11"/>')
    put(f'<text x="{X0 + 274}" y="{TOP - 6}">library eras</text>')

    # the two requested attrs
    for i, (attr, runs) in enumerate(attrs):
        cy = y_attr + i * ROW_H
        put(
            f'<text class="head" x="{X0 - 8}" y="{cy + BAR_H}" '
            f'text-anchor="end">{attr}</text>'
        )
        for lo, hi in runs:
            dl, dr = clamp(day(lo)), clamp(day(hi))
            if dl >= dr:
                continue
            put(
                f'<rect class="hit" x="{x(dl):.1f}" y="{cy}" '
                f'width="{max(x(dr) - x(dl), BAR_H):.1f}" height="{BAR_H}" rx="3.5"/>'
            )

    # the plan pins on the python row: coherent (solid) and free (hollow),
    # with the retreat arrow between them
    py_cy = y_attr + 1 * ROW_H + BAR_H / 2
    fx, cx = x(day(FREE_OFF)), x(day(COHERENT_OFF))
    put(f'<circle class="free" cx="{fx:.1f}" cy="{py_cy:.1f}" r="4"/>')
    put(f'<circle class="pin" cx="{cx:.1f}" cy="{py_cy:.1f}" r="4.5"/>')
    ay = TOP + 30
    put(
        f'<path class="arrow" d="M {fx:.1f} {py_cy - 6:.1f} C {fx:.1f} {ay:.1f}, '
        f'{cx:.1f} {ay:.1f}, {cx + 2:.1f} {py_cy - 7:.1f}" '
        f'marker-end="url(#tip)"/>'
    )
    put(
        '<defs><marker id="tip" markerWidth="7" markerHeight="7" refX="5" refY="3.5" '
        'orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#cf5d28"/></marker></defs>'
    )
    mid = (fx + cx) / 2
    put(
        f'<text class="wtext" x="{mid:.1f}" y="{ay - 6:.1f}" text-anchor="middle">'
        f"--one zstd --one openssl retreats python 16 months</text>"
    )
    put(
        f'<text x="{cx:.1f}" y="{py_cy + 20:.1f}" text-anchor="middle">'
        f"3.10.4 (r{COHERENT_OFF})</text>"
    )
    put(
        f'<text x="{fx:.1f}" y="{py_cy + 20:.1f}" text-anchor="middle">'
        f"3.10.12 (r{FREE_OFF})</text>"
    )

    # the era strips
    for i, lib in enumerate(LIBS):
        cy = y_era + i * ROW_H
        put(
            f'<text class="head" x="{X0 - 8}" y="{cy + ERA_H - 3}" '
            f'text-anchor="end">{lib}</text>'
        )
        eras = [e for e in index.eras_of(lib) if day(e[2]) >= t0 and day(e[1]) <= t1]
        for k, (version, lo, hi) in enumerate(sorted(eras, key=lambda e: e[1])):
            dl, dr = clamp(day(lo)), clamp(day(hi))
            bx, bw = x(dl), max(x(dr) - x(dl), 1.5)
            put(
                f'<rect class="era{" odd" if k % 2 else ""}" x="{bx:.1f}" '
                f'y="{cy}" width="{bw:.1f}" height="{ERA_H}"/>'
            )
            if bw >= MIN_LABEL_W:
                put(
                    f'<text class="etext" x="{bx + bw / 2:.1f}" y="{cy + ERA_H - 3}" '
                    f'text-anchor="middle">{version}</text>'
                )

    put("</svg>")
    Path(args.out).write_text("\n".join(svg) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
