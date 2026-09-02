#!/usr/bin/env python3
"""Draw the version-lifetime chart for the blog post: python3 minors and
openssl series as horizontal life-bars over the full index, with the
coexistence window for `python3@>=3.10 ^openssl@1.1.*` shaded.

Usage: lifetimes.py --index <multiverse checkout> --out <svg path>
Needs plotnine (nix shell -p 'python3.withPackages (ps: [ps.plotnine])').
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from grail.index import Index  # noqa: E402
from grail.versions import components, sort_key  # noqa: E402

# the validated figure palette (light surface)
BLUE = "#2a78d6"  # runs that satisfy the constraint
ORANGE = "#d8622b"  # the coexistence window
GRAY = "#7d7970"  # every other version: context, deliberately recessive
INK = "#0b0b0b"
INK_2 = "#52514e"


def _union(intervals):
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(lo, hi) for lo, hi in merged]


def _series_rows(index, attr, series_of, matches):
    """Aggregate an attr's versions into (series, lo, hi, match) segments."""
    buckets: dict[str, list] = {}
    hit: dict[str, bool] = {}
    for version in index.versions_of(attr):
        series = series_of(version)
        if series is None:
            continue
        buckets.setdefault(series, []).extend(index.runs_of(attr, version))
        hit[series] = hit.get(series, False) or matches(version)

    rows = []
    for series, intervals in buckets.items():
        for lo, hi in _union(intervals):
            rows.append((series, lo, hi, hit[series]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    index = Index.load(args.index)
    day = lambda off: date.fromisoformat(index.revision(off).date)

    # python3 by minor; >=3.10 satisfies the constraint
    py_minor = lambda v: ".".join(components(v)[:2])
    py_rows = _series_rows(
        index,
        "python3",
        py_minor,
        lambda v: sort_key(v) >= sort_key("3.10"),
    )

    # openssl: 1.0.x and 1.1.x stay distinct, 3.* collapses to one row
    def ssl_series(v):
        c = components(v)
        return "3.x" if c[0] == "3" else ".".join(c[:2]) + ".x"

    ssl_rows = _series_rows(
        index, "openssl", ssl_series, lambda v: v.startswith("1.1.")
    )

    # the coexistence window: revisions where both constraints hold
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
    print(f"window: r{wlo}..r{whi}  {day(wlo)} .. {day(whi)}")

    import pandas as pd
    from plotnine import (
        aes,
        element_blank,
        element_line,
        element_rect,
        element_text,
        facet_grid,
        geom_rect,
        geom_segment,
        ggplot,
        labs,
        scale_color_manual,
        scale_x_datetime,
        scale_y_discrete,
        theme,
        theme_minimal,
    )

    frames = []
    for attr, rows in (("python3", py_rows), ("openssl", ssl_rows)):
        for series, lo, hi, match in rows:
            frames.append(
                {
                    "attr": attr,
                    "series": series,
                    "start": pd.Timestamp(day(lo)),
                    "end": pd.Timestamp(day(hi)),
                    "match": "constraint" if match else "other versions",
                }
            )
    df = pd.DataFrame(frames)

    # newest series at the top of each facet
    order = {}
    for attr in ("python3", "openssl"):
        keys = sorted(set(df[df.attr == attr].series), key=sort_key)
        order[attr] = keys
    df["series"] = pd.Categorical(
        df["series"], categories=order["openssl"] + order["python3"]
    )
    df["attr"] = pd.Categorical(df["attr"], categories=["python3", "openssl"])

    win = pd.DataFrame(
        {
            "attr": pd.Categorical(
                ["python3", "openssl"], categories=["python3", "openssl"]
            ),
            "xmin": [pd.Timestamp(day(wlo))] * 2,
            "xmax": [pd.Timestamp(day(whi))] * 2,
        }
    )

    plot = (
        ggplot(df)
        + geom_rect(
            win,
            aes(xmin="xmin", xmax="xmax"),
            ymin=-float("inf"),
            ymax=float("inf"),
            fill=ORANGE,
            alpha=0.14,
        )
        + geom_segment(
            aes(x="start", xend="end", y="series", yend="series", color="match"),
            size=2.6,
            lineend="round",
        )
        + scale_color_manual(
            values={"constraint": BLUE, "other versions": GRAY}, name=""
        )
        + scale_y_discrete()
        + scale_x_datetime(date_breaks="2 years", date_labels="%Y")
        + facet_grid("attr ~ .", scales="free_y", space="free_y")
        + labs(
            title="python3@>=3.10 ^ openssl@1.1.*",
            subtitle=(
                f"version lifetimes in nixos-unstable, 2012–2026; the shaded band "
                f"is every revision where both hold: {day(wlo)} to {day(whi)}"
            ),
            x="",
            y="",
        )
        + theme_minimal()
        + theme(
            figure_size=(9.5, 6.2),
            text=element_text(color=INK_2),
            plot_title=element_text(color=INK, size=13, family="monospace"),
            plot_subtitle=element_text(color=INK_2, size=9.5),
            strip_text=element_text(color=INK, size=10, weight="bold"),
            axis_text=element_text(color=INK_2, size=8.5),
            panel_grid_major_y=element_blank(),
            panel_grid_minor=element_blank(),
            panel_grid_major_x=element_line(color="#e5e3df", size=0.4),
            plot_background=element_rect(fill="white", color=None),
            legend_position="top",
            legend_title=element_blank(),
        )
    )
    plot.save(args.out, verbose=False)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
