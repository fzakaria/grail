"""Turn a parsed query plus the index into ASP facts for asp/solve.lp.

Only the attrs the query names produce facts, so grounding stays in the
hundreds of atoms regardless of index size. Range evaluation happens here,
in Python, against compareVersions order; the solver only ever sees the
versions that already passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .index import Index
from .specs import Query, Spec
from .versions import sort_key


class InfeasibleError(Exception):
    """A spec that no fact emission can serve; .reasons lists one line each."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass
class SpecFacts:
    """One spec resolved against the index: which versions survive."""

    sid: str
    gid: str
    spec: Spec
    # version -> (rank, clamped runs)
    versions: dict[str, tuple[int, list[tuple[int, int]]]] = field(default_factory=dict)


def _clamp(runs, lo_bound, hi_bound):
    clamped = []
    for lo, hi in runs:
        lo2, hi2 = max(lo, lo_bound), min(hi, hi_bound)
        if lo2 <= hi2:
            clamped.append((lo2, hi2))
    return clamped


def resolve_specs(
    query: Query, index: Index, lo_bound: int, hi_bound: int
) -> list[SpecFacts]:
    """Match every spec's range against the index, or raise InfeasibleError."""
    out: list[SpecFacts] = []
    problems: list[str] = []

    sid = 0
    for g, group in enumerate(query.groups):
        for spec in group.specs:
            sf = SpecFacts(sid=f"s{sid}", gid=f"g{g}", spec=spec)
            sid += 1

            if not index.has_attr(spec.attr):
                problems.append(f"{spec.attr} is not in the index")
                continue

            # rank versions in compareVersions order across the whole attr,
            # so "newer" means the same thing the index means by it
            ranked = sorted(index.versions_of(spec.attr), key=sort_key)
            for rank, version in enumerate(ranked):
                if not spec.matches(version):
                    continue
                runs = _clamp(index.runs_of(spec.attr, version), lo_bound, hi_bound)
                if runs:
                    sf.versions[version] = (rank, runs)

            if not sf.versions:
                clamp_note = (
                    ""
                    if (lo_bound, hi_bound) == (0, index.tip)
                    else " inside the date bounds"
                )
                problems.append(
                    f"no version of {spec.attr} matches"
                    f"{'' if spec.range is None else ' the range'}{clamp_note}"
                )
                continue

            out.append(sf)

    if problems:
        raise InfeasibleError(problems)
    return out


def _q(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def emit(spec_facts: list[SpecFacts], index: Index, libs: list[str]) -> str:
    """The facts block handed to clingo alongside asp/solve.lp. `libs` are
    the --one attrs, whose version eras become libera facts."""
    lines = []

    for sf in spec_facts:
        lines.append(f"spec({sf.sid}).")
        # names the opaque spec id for humans and tooling; no rule reads it
        lines.append(f"attrname({sf.sid}, {_q(sf.spec.attr)}).")
        lines.append(f"group({sf.gid}, {sf.sid}).")
        for version, (rank, runs) in sf.versions.items():
            lines.append(f"allowed({sf.sid}, {_q(version)}, {rank}).")
            for lo, hi in runs:
                lines.append(f"run({sf.sid}, {_q(version)}, {lo}, {hi}).")

    # version eras per library, keyed by rank so #minimize counts eras
    for lib in libs:
        for k, (_, lo, hi) in enumerate(index.eras_of(lib)):
            lines.append(f"libera({_q(lib)}, {k}, {lo}, {hi}).")

    return "\n".join(lines) + "\n"


def one_rule(lib: str) -> str:
    """The hard clause --one <attr> appends: its eras must not mix."""
    return f":- usedlib({_q(lib)}, K1), usedlib({_q(lib)}, K2), K1 < K2.\n"
