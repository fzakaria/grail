"""Drive clingo over asp/solve.lp plus the emitted facts, and turn the
optimum model into a plan. Handles the two flavors of "no": a spec no
fact emission can serve (explained before clingo ever runs) and an UNSAT
solve (explained by interval analysis or a relaxed re-solve)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .facts import ONE_GLIBC_RULE, InfeasibleError, SpecFacts, emit, resolve_specs
from .index import Index, Revision
from .specs import Query

# clingo prints the optimum as the last witness of the (only) call
_PICK_RE = re.compile(r'pick\((s\d+),"((?:[^"\\]|\\.)*)"\)')
_AT_RE = re.compile(r"at\((g\d+),(\d+)\)")

_DEFAULT_SOLVE_LP = Path(__file__).resolve().parent.parent / "asp" / "solve.lp"


@dataclass
class SolveOptions:
    one_glibc: bool = False
    before: str | None = None  # ISO date, inclusive
    after: str | None = None  # ISO date, inclusive
    clingo_bin: str = field(
        default_factory=lambda: os.environ.get("GRAIL_CLINGO", "clingo")
    )
    solve_lp: Path = field(
        default_factory=lambda: Path(
            os.environ.get("GRAIL_SOLVE_LP", _DEFAULT_SOLVE_LP)
        )
    )


@dataclass
class Pin:
    attr: str
    version: str


@dataclass
class GroupPlan:
    revision: Revision
    pins: list[Pin]


@dataclass
class Plan:
    result: str  # "sat" | "unsat"
    revisions: int = 0
    groups: list[GroupPlan] = field(default_factory=list)
    glibcs: list[str] = field(default_factory=list)
    why: str | None = None

    def to_dict(self) -> dict:
        return {
            "result": self.result,
            "revisions": self.revisions,
            "groups": [
                {
                    "revision": {
                        "off": g.revision.off,
                        "rev": g.revision.rev,
                        "label": g.revision.label,
                        "date": g.revision.date,
                    },
                    "pins": [{"attr": p.attr, "version": p.version} for p in g.pins],
                }
                for g in self.groups
            ],
            "glibcs": self.glibcs,
            "why": self.why,
        }


def _run_clingo(opts: SolveOptions, facts: str, extra_rules: str = "") -> dict:
    proc = subprocess.run(
        [opts.clingo_bin, "--outf=2", "--opt-mode=opt", str(opts.solve_lp), "-"],
        input=facts + extra_rules,
        capture_output=True,
        text=True,
    )
    # clingo's exit code is a bitmask (10 SAT, 20 UNSAT, +1 interrupt);
    # the JSON Result field is the reliable signal
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"clingo produced no JSON (exit {proc.returncode}): {proc.stderr.strip()}"
        )


def _model_atoms(answer: dict) -> list[str] | None:
    if answer.get("Result") not in ("SATISFIABLE", "OPTIMUM FOUND"):
        return None
    witnesses = answer["Call"][0].get("Witnesses")
    if not witnesses:
        return None
    return witnesses[-1]["Value"]


def _spec_union(sf: SpecFacts) -> list[tuple[int, int]]:
    """The union of a spec's allowed runs, as merged sorted intervals."""
    runs = sorted(r for _, rs in sf.versions.values() for r in rs)
    merged: list[list[int]] = []
    for lo, hi in runs:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(lo, hi) for lo, hi in merged]


def _describe(sf: SpecFacts) -> str:
    if len(sf.versions) == 1:
        return f"{sf.spec.attr} {next(iter(sf.versions))}"
    return sf.spec.text or sf.spec.attr


def _never_overlapped(spec_facts: list[SpecFacts], index: Index) -> str | None:
    """Find a coexistence pair whose allowed lifetimes never intersect."""
    by_group: dict[str, list[SpecFacts]] = {}
    for sf in spec_facts:
        by_group.setdefault(sf.gid, []).append(sf)

    for members in by_group.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                ua, ub = _spec_union(a), _spec_union(b)
                if any(lo1 <= hi2 and lo2 <= hi1 for lo1, hi1 in ua for lo2, hi2 in ub):
                    continue
                # order the pair by time for the message
                if ua[-1][1] > ub[-1][1]:
                    a, b, ua, ub = b, a, ub, ua
                last = index.revision(ua[-1][1])
                first = index.revision(ub[0][0])
                return (
                    f"{_describe(a)} and {_describe(b)} never overlapped: "
                    f"{_describe(a)} was last alive {last.date} (r{last.off}), "
                    f"{_describe(b)} first alive {first.date} (r{first.off})"
                )
    return None


def _glibcs_of(offsets: list[int], index: Index) -> list[str]:
    names = []
    for version, lo, hi in index.glibc_eras():
        if any(lo <= off <= hi for off in offsets):
            names.append(version)
    return sorted(
        set(names),
        key=lambda v: [version for version, _, _ in index.glibc_eras()].index(v),
    )


def _plan_from_atoms(
    atoms: list[str], spec_facts: list[SpecFacts], index: Index
) -> Plan:
    picked: dict[str, str] = {}
    for m in _PICK_RE.finditer(" ".join(atoms)):
        picked[m.group(1)] = m.group(2).replace('\\"', '"')
    where: dict[str, int] = {}
    for m in _AT_RE.finditer(" ".join(atoms)):
        where[m.group(1)] = int(m.group(2))

    groups: dict[str, GroupPlan] = {}
    for sf in spec_facts:
        off = where[sf.gid]
        gp = groups.setdefault(sf.gid, GroupPlan(index.revision(off), []))
        gp.pins.append(Pin(sf.spec.attr, picked[sf.sid]))

    offsets = sorted({g.revision.off for g in groups.values()})
    return Plan(
        result="sat",
        revisions=len(offsets),
        groups=[
            groups[g] for g in sorted(groups, key=lambda g: groups[g].revision.off)
        ],
        glibcs=_glibcs_of(offsets, index),
    )


def solve(query: Query, index: Index, opts: SolveOptions | None = None) -> Plan:
    opts = opts or SolveOptions()

    # date bounds become offset bounds once, here
    lo_bound, hi_bound = 0, index.tip
    if opts.after is not None:
        first = index.first_on_or_after(opts.after)
        if first is None:
            return Plan(result="unsat", why=f"no revision on or after {opts.after}")
        lo_bound = first
    if opts.before is not None:
        last = index.last_on_or_before(opts.before)
        if last is None:
            return Plan(result="unsat", why=f"no revision on or before {opts.before}")
        hi_bound = last

    try:
        spec_facts = resolve_specs(query, index, lo_bound, hi_bound)
    except InfeasibleError as e:
        return Plan(result="unsat", why="; ".join(e.reasons))

    facts = emit(spec_facts, index)
    extra = ONE_GLIBC_RULE if opts.one_glibc else ""
    atoms = _model_atoms(_run_clingo(opts, facts, extra))

    if atoms is not None:
        return _plan_from_atoms(atoms, spec_facts, index)

    # UNSAT: explain. A coexistence group whose members never overlapped is
    # the common cause and is provable from the intervals alone.
    why = _never_overlapped(spec_facts, index)
    if why is None and opts.one_glibc:
        # relax the glibc clause; if that solves, the eras were the problem
        relaxed = _model_atoms(_run_clingo(opts, facts, ""))
        if relaxed is not None:
            plan = _plan_from_atoms(relaxed, spec_facts, index)
            eras = ", ".join(plan.glibcs)
            why = (
                f"satisfiable only by mixing glibc eras ({eras}); "
                f"--one-glibc forbids that"
            )
    return Plan(result="unsat", why=why or "no model satisfies the query")
