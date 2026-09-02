"""Version ordering with the exact semantics of Nix's builtins.compareVersions.

The reference is nextComponent/componentsLT in Nix's names.cc: a version
splits into components that are maximal runs of digits or maximal runs of
non-digits, with '.' and '-' acting as separators that appear in no
component. Ordering rules, in the order componentsLT checks them:

  - two numeric components compare as integers
  - an empty component is smaller than a numeric one
  - "pre" is smaller than anything except "pre"
  - a numeric component is larger than any non-numeric one
  - anything else compares as a plain string (so "" < "rc": only pre is
    special, an -rc suffix sorts AFTER the release)
"""

from __future__ import annotations

# The separator characters nextComponent skips over.
_SEPARATORS = ".-"

# The one magic component that sorts before the release it suffixes.
_PRE = "pre"


def components(version: str) -> list[str]:
    """Split a version string the way Nix's nextComponent does."""
    parts: list[str] = []
    i = 0
    n = len(version)
    while i < n:
        # skip separators between components
        if version[i] in _SEPARATORS:
            i += 1
            continue

        # a component is a run of digits, or a run of everything else
        start = i
        if version[i].isdigit():
            while i < n and version[i].isdigit():
                i += 1
        else:
            while i < n and not version[i].isdigit() and version[i] not in _SEPARATORS:
                i += 1
        parts.append(version[start:i])
    return parts


def _component_less(a: str, b: str) -> bool:
    """componentsLT from names.cc, verbatim in Python."""
    a_num = int(a) if a.isdigit() else None
    b_num = int(b) if b.isdigit() else None

    if a_num is not None and b_num is not None:
        return a_num < b_num
    if a == "" and b_num is not None:
        return True
    if a == _PRE and b != _PRE:
        return True
    if b == _PRE:
        return False
    if b_num is not None:
        return True
    if a_num is not None:
        return False
    return a < b


def compare(a: str, b: str) -> int:
    """Return <0, 0 or >0 exactly as builtins.compareVersions would."""
    ca = components(a)
    cb = components(b)

    # walk both component lists, padding the shorter with ""
    for i in range(max(len(ca), len(cb))):
        x = ca[i] if i < len(ca) else ""
        y = cb[i] if i < len(cb) else ""
        if x == y:
            continue
        if _component_less(x, y):
            return -1
        if _component_less(y, x):
            return 1
        # components differ as strings but neither is less: treat as equal
        # (cannot happen with componentsLT's total order, kept for safety)
    return 0


def sort_key(version: str):
    """A sort key consistent with compare(), for ranking versions."""
    import functools

    return functools.cmp_to_key(compare)(version)
