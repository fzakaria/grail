# The query grammar

This file is normative; `grail/specs.py` implements it and
`tests/test_specs.py` exercises every production.

```
query      ::= group ( ws group )*
group      ::= spec ( ws "^" spec )*
spec       ::= attr [ "@" range ]
attr       ::= segment ( "." segment )*
segment    ::= [A-Za-z0-9_+-]+
range      ::= alt ( "||" alt )*
alt        ::= term ( "," term )*
term       ::= cmp version
             | version ".." version
             | version ".x"
             | version ".*"
             | version
cmp        ::= ">=" | ">" | "<=" | "<" | "="
version    ::= [A-Za-z0-9._+-]+
```

## Semantics

Whitespace separates independent groups. `^` chains the next spec onto the
previous group, and a group is a **coexistence** claim: every member must
resolve at one shared revision — one moment in nixpkgs history where all of
them were simultaneously true.

```
python3@>=3.10 ^openssl@1.1.*     one revision serves both
python3@>=3.10 openssl@1.1.*      independent; the solver may still merge
                                  them onto one revision, and prefers to
```

Version ordering is Nix's `builtins.compareVersions`, reimplemented
byte-for-byte in `grail/versions.py` (the quirks included: only `pre` sorts
before its release; `1.0-rc1` sorts after `1.0`).

- A bare version is a component-wise prefix, exactly the semantics
  `mvs solve` documents: `3.8` accepts `3.8.9`, refuses `3.81` and `3.1`.
  `.x` and `.*` are the same thing spelled explicitly.
- `a..b` is an inclusive interval. The upper endpoint is prefix-inclusive,
  so `3.10..3.11` keeps `3.11.9`.
- `,` is conjunction, `||` alternation; `||` binds looser:
  `>=3.9,<3.10||=3.12.4` reads as (>=3.9 and <3.10) or exactly 3.12.4.
- An attr may be a nested-set path (`jetbrains.idea`), one key of the flat
  index exactly as multiverse stores it.

Date bounds are CLI flags rather than sigils: `--before 2023-01-01` and
`--after 2020-06-01` clamp the candidate revisions, inclusively, before the
solver runs. `--one-glibc` adds a hard constraint that the chosen revisions
all fall in one glibc era.
