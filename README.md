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
newest versions, then fewest glibc eras, then freshest builds.
`--one-glibc` turns era-mixing into a hard error.

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
