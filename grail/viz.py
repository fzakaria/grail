"""Render a solved plan as a graph via clingraph: the plan becomes facts,
asp/viz.lp (an ASP program) decides what the picture is, graphviz draws
it. The solver's answer is visualized by the same formalism that found it."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .index import Index
from .solve import Plan

_VIZ_LP = Path(__file__).resolve().parent.parent / "asp" / "viz.lp"


class VizError(RuntimeError):
    pass


def _lib_at(index: Index, lib: str, off: int) -> str | None:
    for version, lo, hi in index.eras_of(lib):
        if lo <= off <= hi:
            return version
    return None


def plan_facts(plan: Plan, index: Index) -> str:
    """The plan as clingraph input facts, labels precomposed."""
    if plan.result != "sat":
        raise VizError(f"cannot draw an unsatisfiable plan: {plan.why}")

    # every era-tracked lib (glibc, plus --one attrs) labels the revision
    tracked = [lib for lib, _ in plan.libs] or ["glibc"]

    lines = []
    pin_id = 0
    for gi, group in enumerate(plan.groups):
        rev = group.revision
        label = f"r{rev.off} · {rev.date}"
        for lib in tracked:
            version = _lib_at(index, lib, rev.off)
            if version is not None:
                label += f"\\n{lib} {version}"
        lines.append(f'revnode(g{gi}, "{label}").')
        for pin in group.pins:
            lines.append(f'pinnode(p{pin_id}, g{gi}, "{pin.attr} {pin.version}").')
            pin_id += 1
    return "\n".join(lines) + "\n"


def render(plan: Plan, index: Index, out: str | Path) -> None:
    """Write the plan graph to `out`; .dot gives graphviz source, anything
    else renders SVG."""
    out = Path(out)
    fmt = "dot" if out.suffix == ".dot" else "svg"
    clingraph = os.environ.get("GRAIL_CLINGRAPH", "clingraph")

    with tempfile.TemporaryDirectory() as tmp:
        facts = Path(tmp) / "plan.lp"
        facts.write_text(plan_facts(plan, index))
        # graphviz source goes to stdout; a rendered image goes to a file
        mode = ["--out=dot"] if fmt == "dot" else ["--out=render", "--format=svg"]
        proc = subprocess.run(
            [
                clingraph,
                str(facts),
                f"--viz={_VIZ_LP}",
                "--type=digraph",
                *mode,
                f"--dir={tmp}",
                "--name-format=plan",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise VizError(f"clingraph failed: {proc.stderr.strip()}")

        if fmt == "dot":
            out.write_text(proc.stdout)
            return
        rendered = Path(tmp) / "plan.svg"
        if not rendered.exists():
            raise VizError(f"clingraph produced no {rendered.name}")
        out.write_bytes(rendered.read_bytes())
