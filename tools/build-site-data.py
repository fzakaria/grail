#!/usr/bin/env python3
"""Emit the static data tree the search site solves against, from a
multiverse checkout (or flake input):

    data/attrs.json          every attr name, sorted — the autocomplete corpus
    data/revisions.json      [[date, rev12], ...] by offset — labels and dates
    data/history/<xx>.json   history shards: attr -> version -> runs, sharded
                             by the first two characters of the attr so a
                             query fetches kilobytes, not the 8 MB index

Runs keep the index's shape ([lo, hi], nested for holes, null = open tip);
the browser closes the tip against revisions.length exactly like grail does.

Usage: build-site-data.py --index <multiverse checkout> --out <dir>
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def shard_of(attr: str) -> str:
    """Two-character shard key; anything outside [a-z0-9] folds to '_'."""
    key = attr.lower()[:2].ljust(2, "_")
    return "".join(c if c.isascii() and (c.isalnum()) else "_" for c in key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    index = Path(args.index)
    out = Path(args.out)

    revisions = json.loads((index / "revisions.json").read_text())
    history = json.loads((index / "index" / "history.json").read_text())
    attrs = history["attrs"]

    (out / "history").mkdir(parents=True, exist_ok=True)

    (out / "attrs.json").write_text(json.dumps(sorted(attrs), separators=(",", ":")))
    (out / "revisions.json").write_text(
        json.dumps(
            [[r["date"], r["rev"][:12]] for r in revisions], separators=(",", ":")
        )
    )

    shards: dict[str, dict] = defaultdict(dict)
    for attr, versions in attrs.items():
        shards[shard_of(attr)][attr] = versions
    for key, content in shards.items():
        (out / "history" / f"{key}.json").write_text(
            json.dumps(content, separators=(",", ":"))
        )

    print(
        f"wrote {len(attrs)} attrs across {len(shards)} shards, "
        f"{len(revisions)} revisions -> {out}"
    )


if __name__ == "__main__":
    main()
