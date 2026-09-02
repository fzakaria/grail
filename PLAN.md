# grail — version-range concretization over nixpkgs-multiverse

`grail` answers queries like `python3@>=3.10 ^openssl@1.1.*` against the
14-year nixpkgs-multiverse index using clingo (Answer Set Programming), and
turns the answer into things Nix can consume: a standard `multiverse.lock`,
or a `mkDerivation` whose inputs were chosen by the solver.

The name comes from the pitch: version ranges are the holy grail of nixpkgs.
Nixpkgs never needed a dependency solver because it has one version per
attribute. The multiverse un-deleted the versions; grail hands Nix the solver
it was proud not to need.

## Why a separate repo, not multiverse

- multiverse has `inputs = { }` on purpose and a greedy exact-pin solver with
  an optimality proof and a self-checkable certificate. Both properties are
  worth protecting. grail needs inputs (nixpkgs for clingo, multiverse for
  the index) and solves an NP-hard superset where no greedy proof exists.
- multiverse's own docs draw the line: exact pins are interval stabbing,
  greedy, O(n log n), provably minimal; versions with holes plus ranges turn
  the problem into hitting set over interval unions, which is NP-hard. grail
  starts exactly where that sentence ends.
- Different maturity. multiverse is done; grail is an experiment. If the
  range solver earns it, `mvs solve` can grow a `--ranges` flag later that
  shells out to (or embeds) the same `solve.lp`.

## What already exists and is reused, not rebuilt

| Piece                         | Source       | Role in grail                                                                                                                                                                                                             |
| ----------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `revisions.json`              | multiverse   | offset -> {rev, date, name, narHash}; 1,541 rows                                                                                                                                                                          |
| `index/history.json`          | multiverse   | attr -> version -> lifetime runs `[lo, hi]`, nested runs for holes, `null` = open tip                                                                                                                                     |
| `mv.at <selector>`            | multiverse   | materialize a revision as a real nixpkgs                                                                                                                                                                                  |
| `mv.pinPlan` / `mv.solvePins` | multiverse   | exact-pin minimization (greedy, proven) — grail defers to it when a query has no ranges                                                                                                                                   |
| `multiverse.lock` v1          | mvs          | `{version: 1, pins: {attr: {rev, label, version, date}}}` — grail's lock output IS this format, so `mv.readLock`, the NixOS/darwin/home-manager modules, and `mvs lock status` all work on a grail-written lock unchanged |
| glibc lifetimes               | history.json | `glibc` is an indexed attr, so "which glibc reigned at revision R" is metadata — no ELF analysis needed for the coexistence tier                                                                                          |

## Architecture

```
specs ── grail/specs.py ──> AST
                              │
history.json ─ grail/facts.py ┴──> facts.lp ┐
                                            ├─ clingo --outf=2 ──> model
asp/solve.lp (static rules) ────────────────┘                        │
                              grail/solve.py <── JSON answer set ────┘
                                            │
                        ┌───────────────────┼──────────────────────┐
                   grail solve         grail lock              IFD (Nix)
                 (human / --json)   (multiverse.lock v1)   nix/solve-ifd.nix
                                                                │
                                                     grail.lib.mkDerivation
                                                     inputs via mv.at,
                                                     stdenv from the
                                                     coexistence revision
```

Driver is Python (stdlib only) shelling out to the `clingo` binary with
`--outf=2` (JSON output). No clingo language bindings to package; the same
driver runs on the CLI and inside the IFD sandbox.

## Query language

Spack-flavored sigils, our own grammar. BNF (docs/grammar.md is normative):

```
query      ::= group ( ws group )*
group      ::= spec ( ws "^" spec )*        ; ^ chains specs into one
                                            ; coexistence group: they must
                                            ; resolve to a single revision
spec       ::= attr [ "@" range ]
attr       ::= segment ( "." segment )*     ; nested sets: "jetbrains.idea"
segment    ::= [A-Za-z0-9_+-]+
range      ::= alt ( "||" alt )*            ; alternation
alt        ::= term ( "," term )*           ; conjunction
term       ::= cmp version
             | version ".." version         ; inclusive interval
             | version ".x"                 ; prefix match (mvs-compatible:
             | version ".*"                 ;  3.8 matches 3.8.9, not 3.81)
             | version                      ; bare = prefix match, exactly
                                            ;  the semantics mvs solve has
cmp        ::= ">=" | ">" | "<=" | "<" | "="
version    ::= [A-Za-z0-9._+-]+             ; opaque; compared with Nix's
                                            ; builtins.compareVersions order
```

Examples:

```
grail solve 'python3@>=3.10 ^openssl@1.1.*'      # one revision, both hold
grail solve 'python3@3.10..3.12 ripgrep@>=14'    # independent, minimized
grail solve 'ffmpeg@4.* || ffmpeg@5.*'           # alternation
grail lock  'python3@>=3.10 ^openssl@1.1.*'      # writes multiverse.lock
```

CLI flags, not sigils: `--before DATE` / `--after DATE` clamp candidate
revisions; `--one-glibc` (multi-group queries) forbids mixing glibc eras;
`--all-models N` prints alternatives. Version ordering implements
`builtins.compareVersions` semantics in Python (component split, numeric
vs alpha, letter < digit) so ranks agree with `mv.sortVersions`.

## ASP encoding (asp/solve.lp)

Facts, emitted per query by facts.py — only for the attrs the query names,
so grounding stays in the hundreds of atoms:

```prolog
run(A, V, Lo, Hi).        % one lifetime run; open tip closed to tipOffset
vrank(A, V, K).           % position in compareVersions order
allowed(A, V).            % versions passing the range, from the front-end
group(G, A).              % coexistence group membership
tip(T).                   % newest offset
glibcat(R, K).            % glibc era rank at revision R (from history.json)
```

Rules (the whole program is ~40 lines):

```prolog
% choose exactly one version per requested attr
1 { pick(A, V) : allowed(A, V) } 1 :- group(_, A).

% a group resolves at exactly one revision inside every member's run
1 { at(G, R) : rev(R) } 1 :- group(G, _).
ok(G, R) :- at(G, R), group(G, A), pick(A, V), run(A, V, Lo, Hi),
            Lo <= R, R <= Hi.
:- at(G, R), group(G, A), pick(A, V), not member(A, V, R).
member(A, V, R) :- run(A, V, Lo, Hi), rev(R), Lo <= R, R <= Hi.

used(R)  :- at(_, R).
usedglibc(K) :- used(R), glibcat(R, K).

% objectives, lexicographic:
#minimize { 1@4, R : used(R) }.                 % fewest revisions
#maximize { K@3, A : pick(A, V), vrank(A, V, K) }.  % newest versions
#minimize { 1@2, K : usedglibc(K) }.            % fewest glibc eras
#maximize { R@1 : used(R) }.                    % freshest builds
```

`--one-glibc` adds the hard clause
`:- usedglibc(K1), usedglibc(K2), K1 < K2.`

Unsat handling: on UNSAT, re-solve with the coexistence constraint made soft
(weighted) and report the nearest miss — which pair of constraints never
overlapped, and the closest revision window. This is the feature no other
package tool has, because no other tool has the historical index.

Exact-pin queries (no ranges, no groups) bypass clingo entirely and call
`mv.pinPlan` semantics — the greedy proof is better than a solver's word,
and the two paths cross-check each other in tests.

## Lock and IFD

`grail lock` writes `multiverse.lock` version 1, byte-compatible with what
`mvs lock` writes: pin = `{rev, label, version, date}` where label is
`YYYY-MM-DD-<12hex>` from revisions.json. Everything downstream of a lock
file (readLock, modules, `mvs lock status`) is inherited for free.

IFD (`nix/solve-ifd.nix`): the solve runs as a derivation —
inputs are `${multiverse}/index/history.json`, `${multiverse}/revisions.json`,
the grail sources, clingo and python3 from nixpkgs; output is `solution.json`;
`builtins.fromJSON (builtins.readFile drv)` imports it. The resolver is
itself a derivation: hermetic, cached, and pure-eval-compatible.

`grail.lib.mkDerivation` (nix/mkDerivation.nix):

```nix
grail.lib.mkDerivation {
  pname = "demo";
  specs = "python3@>=3.10 ^openssl@1.1.*";
  src = ./.;
  # ...ordinary mkDerivation arguments
}
```

Coexistence groups resolve to one revision R; `mv.at label` materializes it;
solved attrs become `buildInputs`; **stdenv comes from R too**, so compiler,
glibc and inputs are one time-consistent world. Multiple groups mean multiple
`mv.at` instances; stdenv comes from the newest used revision and the
solver's glibc objective keeps the mix honest. A `lockFile` argument accepts
a pre-solved lock to skip IFD.

## glibc and the ELF fact tiers

v1 ships tier 0 entirely from metadata:

- Coexistence groups: same revision means same glibc by construction.
- Across groups: `glibcat(R, K)` facts from history.json drive the
  fewest-glibc-eras objective and `--one-glibc`.

Tier 1 is prototyped, not wired into the solver: `tools/elf-facts.py` reads
a store path and emits facts —

- `DT_NEEDED` sonames (which deps are ABI-bearing; whether a second libc is
  being dragged in),
- `.gnu.version_r` (verneed): the exact `GLIBC_x.y` / `GLIBCXX_x.y` /
  `CXXABI_x.y` version demands per needed soname,
- `DT_RUNPATH` and `PT_INTERP` (where a second glibc would sneak from; which
  loader runs the final image).

Is verneed the whole story? For glibc/libstdc++ mixing, essentially yes —
verneed carries the demand side and glibc's symbol versioning is the
compatibility contract. Three companions matter: DT_NEEDED (to see a second
libc coming and classify ABI-bearing deps), the loader/RUNPATH pair (the
mechanism by which two libcs end up in one process), and, for mixing
arbitrary libraries across revisions (curl-from-A against openssl-from-B),
export/import matching — undefined dynsyms on one side against `.gnu.version_d`
definitions on the other, which is sqlelf territory. The honest caveat:
symbol presence is not ABI; a struct layout change under an unbumped soname
is invisible to all of this. Tier 1 facts are properties of immutable store
paths, so the fact cache is append-only and computed at most once per path
(narinfo references give the coarse fact with zero NAR bytes; streamed NAR
prefixes give verneed for megabytes, not closures). Tier 2 (CEGAR-style
refine-on-demand via clingo multi-shot) is design only — docs/glibc.md.

## Testing

Test-first where the shape allows. All tests run in `nix flake check`.

- `tests/test_specs.py` — grammar: every BNF production, precedence of
  `||` vs `,`, prefix semantics matching mvs (`3.8` rejects 3.81), nested
  attrs, rejection of malformed specs.
- `tests/test_versions.py` — compareVersions parity table (cases mirrored
  against `nix eval` output, recorded as fixtures).
- `tests/test_solve.py` — golden solves against `tests/fixtures/mini-index/`
  (a hand-written 20-revision index with holes, an open tip, and a fake
  glibc lifetime): coexistence found, coexistence UNSAT with nearest-miss,
  multi-group minimization, one-glibc, alternation, date clamps.
- `tests/test_lock.py` — lock output byte-validates against the v1 schema
  and round-trips through a vendored copy of the readLock contract.
- eval test: `nix/checks.nix` runs the IFD solve on the mini-index inside
  the sandbox and asserts on the imported plan (no network).
- cross-check: for exact-pin queries, grail's answer equals `mv.pinPlan`'s.

## Blog post

Lives in fzakaria.com as `_posts/2026-09-XX-the-holy-grail-of-nixpkgs.md`.
Outline:

1. Cold open: `nixpkgs has never had version ranges. Here is
python3@>=3.10 ^openssl@1.1.* resolving.` Console block first, prose second.
2. Why nixpkgs never needed a solver (one version per attr) and what
   multiverse changed (307k versions — now choice exists, so solving exists).
   Link the multiverse and follows posts.
3. Spack: the one packaging ecosystem that made ranges + a real concretizer
   its identity; clingo since v0.16. Cite Gamblin et al., "Using Answer Set
   Programming for HPC Dependency Solving" (verify venue/arXiv id while
   writing) and point at concretize.lp / libc_compatibility.lp in the tree.
   Then the turn: grail is spack-inspired but solves a different question —
   Spack composes a fresh world; grail finds moments in history where your
   constraints were simultaneously true. You solve for a date, not a graph.
4. Tiny ASP intro via the actual encoding: facts are rows, rules are the
   spec, `1 { } 1` is "pick exactly one", `#minimize` stacks are the policy.
   Full solve.lp inline (it fits).
5. Worked example with real data: the python>=3.10 x openssl 1.1 window
   (offsets ~794..852, mid-2022), figure 1: plotnine interval chart of both
   attrs' lifetimes with the coexistence window highlighted. Figure 2:
   graphviz pipeline (specs -> facts -> clingo -> lock -> mv.at -> store).
6. The derivation: grail.lib.mkDerivation listing + the IFD trick ("the
   resolver is itself a derivation").
7. glibc: why coexistence is the safe default, the two-libcs-in-one-process
   failure, verneed and the fact tiers, narinfo-references-as-free-facts;
   nod to Spack's libc_compatibility.lp doing the forward version of this.
8. Unsat as a feature: "python 3.12 and openssl 1.0 never coexisted; the
   nearest world was ..." — nearest-miss output, real query.
9. Close: what tier 2 unlocks, and the standing invitation to break it.

Figures produced by scripts committed under `tools/figures/` so they
regenerate from the live index (his plotnine/graphviz preference).

## Milestones

1. Repo scaffold, PLAN, mini-index fixture, spec parser + tests.
2. facts.py + solve.lp + solve.py + golden tests; nearest-miss on UNSAT.
3. CLI (`grail solve|lock`), lock writer + tests; real-index smoke run.
4. flake.nix, IFD solve, `grail.lib.mkDerivation`, examples/coexist-demo,
   eval checks.
5. tools/elf-facts.py prototype + docs/glibc.md.
6. Figures + blog post draft in fzakaria.com.

## Future (explicitly out of v1)

- nixmultiverse.com solver page via clingo-wasm (worker, shard-fed facts,
  same solve.lp verbatim).
- Tier 1/2 wired into the solver; elf-facts data release cut like the other
  multiverse artifacts.
- Upstreaming: `mvs solve --ranges` embedding solve.lp via clingo-rs.
- Dependency-closure constraints (specs on transitive deps), which is where
  grounding discipline starts to matter.
- `--one <attr>`: the glibc era constraint generalized to any library
  (openssl, libpython). The invariant is one store path per soname across
  the plan's closures; facts come from narinfo References / the closures
  data releases (which openssl does curl-at-R's closure carry), refined to
  soname granularity by elf_facts. Only matters when mkDerivation links a
  multi-revision plan into one build — build it when someone actually
  wants to do that, not before. No linker metadata catches API-level
  mixing (an SSL* from one openssl handed to another); say so wherever
  this ships.
