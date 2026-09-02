"""The grail CLI: solve prints a plan, lock writes a multiverse.lock.

    grail solve 'python3@>=3.10 ^openssl@1.1.*'
    grail lock  'python3@>=3.10 ^openssl@1.1.*' -o multiverse.lock

The index directory (a nixpkgs-multiverse checkout or its store path) comes
from --index or $GRAIL_INDEX; the flake app bakes the latter in.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .index import Index
from .lock import LockError, write_lock
from .solve import SolveOptions, solve
from .specs import ParseError, parse_query


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "query", nargs="+", help="specs, e.g. 'python3@>=3.10 ^openssl@1.1.*'"
    )
    parser.add_argument(
        "--index",
        default=os.environ.get("GRAIL_INDEX"),
        help="multiverse index directory (default: $GRAIL_INDEX)",
    )
    parser.add_argument(
        "--one-glibc", action="store_true", help="refuse plans that mix glibc eras"
    )
    parser.add_argument(
        "--before", metavar="DATE", help="only revisions on or before this ISO date"
    )
    parser.add_argument(
        "--after", metavar="DATE", help="only revisions on or after this ISO date"
    )


def _print_plan(plan, as_json: bool) -> None:
    if as_json:
        print(json.dumps(plan.to_dict(), indent=2))
        return

    if plan.result != "sat":
        print(f"unsatisfiable: {plan.why}")
        return

    noun = "revision" if plan.revisions == 1 else "revisions"
    print(f"{plan.revisions} {noun}")
    for group in plan.groups:
        rev = group.revision
        print(f"  {rev.label}  ({rev.date}, r{rev.off})")
        for pin in group.pins:
            print(f"    {pin.attr} {pin.version}")
    if plan.glibcs:
        print(f"  glibc: {', '.join(plan.glibcs)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grail")
    sub = parser.add_subparsers(dest="command", required=True)

    p_solve = sub.add_parser("solve", help="resolve a query and print the plan")
    _add_common(p_solve)
    p_solve.add_argument("--json", action="store_true", help="print the plan as JSON")
    p_solve.add_argument(
        "--viz",
        metavar="FILE",
        help="draw the plan via clingraph (.dot for graphviz source, else SVG)",
    )

    p_lock = sub.add_parser("lock", help="resolve a query and write a multiverse.lock")
    _add_common(p_lock)
    p_lock.add_argument(
        "-o",
        "--output",
        default="multiverse.lock",
        help="lock file path (default: ./multiverse.lock)",
    )

    args = parser.parse_args(argv)

    if not args.index:
        parser.error("no index: pass --index or set $GRAIL_INDEX")

    try:
        query = parse_query(" ".join(args.query))
    except ParseError as e:
        parser.error(str(e))

    index = Index.load(args.index)
    opts = SolveOptions(one_glibc=args.one_glibc, before=args.before, after=args.after)
    plan = solve(query, index, opts)

    if args.command == "solve":
        _print_plan(plan, args.json)
        if args.viz and plan.result == "sat":
            from .viz import render

            render(plan, index, args.viz)
            print(f"drew {args.viz}")
        return 0 if plan.result == "sat" else 1

    try:
        write_lock(plan, args.output)
    except LockError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(
        f"wrote {args.output} ({len(plan.groups)} group(s), {plan.revisions} revision(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
