"""The query grammar. docs/grammar.md is the normative BNF; this is it in code.

    query      ::= group ( ws group )*
    group      ::= spec ( ws "^" spec )*
    spec       ::= attr [ "@" range ]
    range      ::= alt ( "||" alt )*
    alt        ::= term ( "," term )*
    term       ::= cmp version | version ".." version
                 | version ".x" | version ".*" | version

A bare version term is a component-wise prefix match, exactly the semantics
mvs solve documents: 3.8 accepts 3.8.9 and refuses 3.81. The upper endpoint
of an interval is prefix-inclusive, so 3.10..3.11 keeps 3.11.9.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .versions import compare, components

# Comparators, longest first so >= is not read as > followed by =.
_COMPARATORS = (">=", "<=", ">", "<", "=")

# Attrs may be nested-set paths like jetbrains.idea; each segment is plain.
_ATTR_RE = re.compile(r"^[A-Za-z0-9_+-]+(\.[A-Za-z0-9_+-]+)*$")

# Version text is opaque to us beyond the component split.
_VERSION_RE = re.compile(r"^[A-Za-z0-9._+-]+$")


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Term:
    """One range term. op is a comparator, 'prefix' or 'interval'."""

    op: str
    version: str
    upper: str | None = None  # interval upper endpoint only

    def matches(self, candidate: str) -> bool:
        if self.op == "prefix":
            return _is_prefix(self.version, candidate)
        if self.op == "interval":
            assert self.upper is not None
            below = compare(candidate, self.upper) <= 0 or _is_prefix(self.upper, candidate)
            return compare(candidate, self.version) >= 0 and below
        c = compare(candidate, self.version)
        return {
            ">=": c >= 0,
            ">": c > 0,
            "<=": c <= 0,
            "<": c < 0,
            "=": c == 0,
        }[self.op]


@dataclass(frozen=True)
class Range:
    """Alternation of conjunctions: any alt may hold, every term in it must."""

    alts: tuple[tuple[Term, ...], ...]

    def matches(self, candidate: str) -> bool:
        return any(all(t.matches(candidate) for t in alt) for alt in self.alts)


@dataclass(frozen=True)
class Spec:
    attr: str
    range: Range | None  # None = any version
    text: str = ""  # the token as typed, for error messages

    def matches(self, candidate: str) -> bool:
        return self.range is None or self.range.matches(candidate)


@dataclass(frozen=True)
class Group:
    """Specs chained with ^: they must resolve at one shared revision."""

    specs: tuple[Spec, ...]


@dataclass(frozen=True)
class Query:
    groups: tuple[Group, ...]

    @property
    def specs(self) -> list[Spec]:
        return [s for g in self.groups for s in g.specs]


def _is_prefix(pattern: str, candidate: str) -> bool:
    """Component-wise prefix: 3.8 accepts 3.8.9 and 3.8, refuses 3.81."""
    p = components(pattern)
    c = components(candidate)
    return len(p) <= len(c) and c[: len(p)] == p


def _parse_term(text: str) -> Term:
    for cmp_op in _COMPARATORS:
        if text.startswith(cmp_op):
            version = text[len(cmp_op) :]
            if not _VERSION_RE.match(version):
                raise ParseError(f"comparator {cmp_op!r} needs a version, got {text!r}")
            return Term(cmp_op, version)

    if ".." in text:
        lo, _, hi = text.partition("..")
        if not (_VERSION_RE.match(lo) and _VERSION_RE.match(hi)):
            raise ParseError(f"interval needs both endpoints, got {text!r}")
        return Term("interval", lo, upper=hi)

    # explicit prefix spellings reduce to the bare-prefix term
    for suffix in (".*", ".x"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    if not _VERSION_RE.match(text):
        raise ParseError(f"malformed version term {text!r}")
    return Term("prefix", text)


def _parse_range(text: str) -> Range:
    alts = []
    for alt_text in text.split("||"):
        if not alt_text:
            raise ParseError(f"empty alternative in range {text!r}")
        terms = tuple(_parse_term(t) for t in alt_text.split(","))
        alts.append(terms)
    return Range(tuple(alts))


def _parse_spec(token: str) -> Spec:
    attr, sep, range_text = token.partition("@")
    if not _ATTR_RE.match(attr):
        raise ParseError(f"malformed attribute name {attr!r}")
    if not sep:
        return Spec(attr, None, token)
    if not range_text:
        raise ParseError(f"{attr!r} has @ but no range")
    return Spec(attr, _parse_range(range_text), token)


def parse_query(text: str) -> Query:
    tokens = text.split()
    if not tokens:
        raise ParseError("empty query")

    groups: list[list[Spec]] = []
    for token in tokens:
        chained = token.startswith("^")
        if chained:
            token = token[1:]
            if not token:
                raise ParseError("dangling ^")
            if not groups:
                raise ParseError("^ must follow a spec to chain onto")
        if not token:
            raise ParseError("empty spec")

        spec = _parse_spec(token)
        if chained:
            groups[-1].append(spec)
        else:
            groups.append([spec])

    return Query(tuple(Group(tuple(g)) for g in groups))
