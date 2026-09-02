"""Loading the multiverse index: revisions.json plus index/history.json.

The history file is the spine grail solves over: attr -> version -> lifetime
runs of revision offsets. A run is [lo, hi]; several runs (a version that
left and came back) nest as [[lo, hi], [lo, hi]]; hi = null means the
version is still alive at the tip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# The one attr whose lifetimes double as era metadata for ABI safety.
GLIBC_ATTR = "glibc"


@dataclass(frozen=True)
class Revision:
    off: int
    rev: str
    date: str
    name: str

    @property
    def label(self) -> str:
        """The mvs label form: YYYY-MM-DD-<12 hex>."""
        return f"{self.date}-{self.rev[:12]}"


class Index:
    def __init__(self, revisions: list[Revision], attrs: dict):
        self.revisions = revisions
        self.attrs = attrs
        self.tip = len(revisions) - 1

    @classmethod
    def load(cls, root: str | Path) -> "Index":
        root = Path(root)
        revisions = [
            Revision(off=i, rev=r["rev"], date=r["date"], name=r.get("name", ""))
            for i, r in enumerate(json.loads((root / "revisions.json").read_text()))
        ]

        # the real multiverse keeps history under index/, the fixture at root
        for candidate in (root / "index" / "history.json", root / "history.json"):
            if candidate.exists():
                history = json.loads(candidate.read_text())
                break
        else:
            raise FileNotFoundError(f"no history.json under {root}")

        count = history.get("revisionCount")
        if count is not None and count != len(revisions):
            raise ValueError(
                f"history covers {count} revisions but revisions.json has {len(revisions)}"
            )
        return cls(revisions, history["attrs"])

    def has_attr(self, attr: str) -> bool:
        return attr in self.attrs

    def versions_of(self, attr: str) -> list[str]:
        return list(self.attrs.get(attr, {}))

    def runs_of(self, attr: str, version: str) -> list[tuple[int, int]]:
        """Lifetime runs as closed [lo, hi] pairs, the open tip closed."""
        raw = self.attrs.get(attr, {}).get(version)
        if raw is None:
            return []

        # a single run is [lo, hi]; several nest one deeper
        runs = raw if raw and isinstance(raw[0], list) else [raw]
        closed = []
        for lo, hi in runs:
            closed.append((lo, self.tip if hi is None else hi))
        return closed

    def revision(self, off: int) -> Revision:
        return self.revisions[off]

    def last_on_or_before(self, date: str) -> int | None:
        """Largest offset whose date is <= the given ISO date."""
        best = None
        for r in self.revisions:
            if r.date <= date:
                best = r.off
        return best

    def first_on_or_after(self, date: str) -> int | None:
        for r in self.revisions:
            if r.date >= date:
                return r.off
        return None

    def eras_of(self, attr: str) -> list[tuple[str, int, int]]:
        """(version, lo, hi) lifetime runs of an attr, as version eras:
        which version of it each revision shipped."""
        eras = []
        for version in self.versions_of(attr):
            for lo, hi in self.runs_of(attr, version):
                eras.append((version, lo, hi))
        eras.sort(key=lambda e: e[1])
        return eras

    def glibc_eras(self) -> list[tuple[str, int, int]]:
        return self.eras_of(GLIBC_ATTR)
