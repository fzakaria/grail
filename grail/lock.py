"""Write a plan as a multiverse.lock, version 1 — the exact shape mvs lock
writes, so mv.readLock, the modules and mvs lock status all consume grail's
output unchanged. A pin is {rev, label, version, date} with rev the 12-hex
commit prefix and label the YYYY-MM-DD-<12 hex> form."""

from __future__ import annotations

import json
from pathlib import Path

from .solve import Plan

LOCK_VERSION = 1


class LockError(ValueError):
    pass


def lock_dict(plan: Plan) -> dict:
    if plan.result != "sat":
        raise LockError(f"cannot lock an unsatisfiable plan: {plan.why}")

    pins: dict[str, dict] = {}
    for group in plan.groups:
        rev = group.revision
        for pin in group.pins:
            if pin.attr in pins:
                raise LockError(
                    f"{pin.attr} appears more than once; a lock has one pin per attr"
                )
            pins[pin.attr] = {
                "rev": rev.rev[:12],
                "label": rev.label,
                "version": pin.version,
                "date": rev.date,
            }
    return {"version": LOCK_VERSION, "pins": pins}


def write_lock(plan: Plan, path: str | Path) -> None:
    Path(path).write_text(json.dumps(lock_dict(plan), indent=2, sort_keys=True) + "\n")
