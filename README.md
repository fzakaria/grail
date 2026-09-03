# grail

Version ranges for nixpkgs, solved by [clingo] over the
[nixpkgs-multiverse] history index.

**Try it at <https://fzakaria.github.io/grail/>** — the whole thing runs in
your browser: clingo compiled to WebAssembly solves `asp/solve.lp`
unmodified against static data shards, with query autocomplete, a drawn
plan graph, and shareable `?q=` links. No server anywhere.

nixpkgs has one version per attribute, which is why it never needed a
dependency solver. The multiverse indexed every version that ever shipped —
307,000+ package-versions across 1,541 revisions of nixos-unstable — and
the moment versions became a choice, solving became a real question. grail
asks it in ranges:

```console
$ grail solve 'python3@>=3.10 ^openssl@1.1.*'
1 revision
  2022-09-12-5f326e2a403e  (2022-09-12, r852)
    python3 3.10.6
    openssl 1.1.1q
  glibc: 2.35
```

`^` chains specs into a **coexistence group**: they must resolve at one
shared revision. grail does not compose a fresh dependency graph the way
[Spack] does — it finds the moments in nixpkgs history when your
constraints were all simultaneously true. You solve for a date, not a
graph. When no such moment exists, the solver says exactly why:

```console
$ grail solve 'python3@3.8.* ^postgresql@13.*'
unsatisfiable: python3@3.8.* and postgresql@13.* never overlapped:
python3@3.8.* was last alive 2021-07-18 (r621), postgresql@13.* first
alive 2021-08-01 (r625)
```

Fourteen days apart, forever.

## Locks

`grail lock` writes a `multiverse.lock`, version 1 — the same file
`mvs lock` writes — so `mv.readLock`, the NixOS/darwin/home-manager
modules and `mvs lock status` consume grail's output unchanged:

```console
$ grail lock 'python3@>=3.10 ^openssl@1.1.*'
wrote multiverse.lock (1 group(s), 1 revision(s))
$ mvs lock status
ATTR     PINNED  LATEST  BEHIND
openssl  1.1.1q  3.6.3   17 versions, 1449 days
python3  3.10.6  3.14.7  29 versions, 1449 days
```

## mkDerivation with version ranges

The resolver is itself a derivation (import-from-derivation): clingo runs
in the sandbox, the plan comes back into eval, and multiverse's `at`
materialises the chosen worlds. stdenv comes from the solved revision, so
compiler, glibc and inputs are one time-consistent world:

```nix
grail.lib.${system}.mkDerivation {
  pname = "demo";
  specs = "python3@>=3.10 ^openssl@1.1.*";
  # ...ordinary mkDerivation arguments
}
```

`nix build .#demo` is exactly that, and prints its world:

```
Python 3.10.6
OpenSSL 1.1.1q  5 Jul 2022
glibc ldd (GNU libc) 2.35
```

## The pieces

| Path                 | What it is                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------- |
| `docs/grammar.md`    | the query BNF: `@` ranges, `^` coexistence, `..`, `\|\|`, prefix semantics matching `mvs solve` |
| `asp/solve.lp`       | the entire solver, ~40 lines of ASP                                                             |
| `docs/encoding.md`   | facts, rules, the lexicographic objective stack, why greedy stops at ranges                     |
| `docs/glibc.md`      | coexistence as the safe default; the verneed fact tiers for mixing worlds                       |
| `tools/elf_facts.py` | tier-1 prototype: DT_NEEDED / `.gnu.version_r` / RUNPATH / interp as ASP facts, stdlib only     |

Exact pins stay multiverse's business: its greedy solver is O(n log n)
with an optimality proof. Ranges are hitting set over interval unions —
NP-hard, the multiverse design doc names the cliff — and that is where
clingo earns its keep. Objectives, lexicographic: fewest revisions, then
newest versions, then fewest mixed library eras, then freshest builds.

## Coherence: `--one <attr>`

`--one <attr>` demands every chosen revision ship the same version of an
attr — the guard against loading two versions of one library in one
process. glibc included: `--one glibc` (shorthand: `--one-glibc`) means
one glibc era or unsat. By default glibc is not constrained at all — its
symbol versioning makes mixing directional, so an unconstrained plan just
reports the link-world minimum.

```console
$ grail solve 'python3@3.10.* postgresql@13.*'
    python3 3.10.12
  glibc: 2.37 serves every input (eras spanned: 2.34, 2.37)
$ grail solve 'python3@3.10.* postgresql@13.*' --one zstd --one openssl
    python3 3.10.4       # one zstd, one openssl — glibc follows for free
  glibc: 2.34
```

When no coherent plan exists, the solver names what would have mixed
(`satisfiable only by mixing zstd 1.5.2/1.5.5, openssl 1.1.1q/3.0.10`).
It guarantees version-level ABI agreement, not one store path — one store
path is what a `^` coexistence group is for. See `docs/glibc.md`.

## Running

```console
$ nix run github:fzakaria/grail -- solve 'go@>=1.21 ^nodejs@>=20'
$ nix flake check   # unit tests + the IFD path, offline
```

`$GRAIL_INDEX` points at any multiverse checkout to solve against a local
or historical index.

[clingo]: https://potassco.org/clingo/
[nixpkgs-multiverse]: https://github.com/fzakaria/nixpkgs-multiverse
[Spack]: https://spack.io/
