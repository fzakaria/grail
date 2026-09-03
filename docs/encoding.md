# The ASP encoding

`asp/solve.lp` is the entire solver — about forty lines. Everything else is
plumbing that gets facts in and a plan out.

## Where the greedy proof ends

multiverse's own `solvePins` is interval stabbing: each exact pin owns one
interval of revisions, minimal cover is greedy, O(n log n), with a
self-certifying disjoint-pin proof. Its design doc also names the cliff:
versions with holes make the feasible set a union of intervals, and minimal
cover over unions is a hitting-set problem — NP-hard. Ranges walk straight
off that cliff: `python3@>=3.10` is a family of lifetimes, the version
choice couples with the revision choice, and the coupling spans every spec
in the query because revisions are shared. So grail hands the search to a
solver built for it and keeps Python for what stays easy: matching ranges,
clamping dates, explaining failure.

## Facts

Emitted per query, only for the attrs the query names (grounding stays in
the hundreds of atoms regardless of index size):

```prolog
spec(s0).                  % one per requested spec
attrname(s0, "python3").   % names the id for humans; no rule reads it
group(g0, s0).             % coexistence group membership
allowed(s0, "3.10.6", 47). % version passed the range; 47 = compareVersions rank
run(s0, "3.10.6", 835, 864). % one lifetime run, clamped to any date bounds
libera("glibc", 9, 824, 1005). % glibc era 9 (2.35) reigned r824..r1005;
                           % emitted per --one attr, glibc when asked
```

## Rules

```prolog
1 { pick(S, V) : allowed(S, V, _) } 1 :- spec(S).

cand(R) :- run(_, _, _, R).
cand(R) :- libera(_, _, _, R).
possible(G, R) :- group(G, S), run(S, V, Lo, Hi), cand(R), Lo <= R, R <= Hi.
1 { at(G, R) : possible(G, R) } 1 :- group(G, _).

alive(S, V, R) :- allowed(S, V, _), run(S, V, Lo, Hi), cand(R), Lo <= R, R <= Hi.
:- at(G, R), group(G, S), pick(S, V), not alive(S, V, R).

used(R) :- at(_, R).
usedlib(L, K) :- used(R), libera(L, K, Lo, Hi), Lo <= R, R <= Hi.
```

Read aloud: pick exactly one version per spec; park each group at one
candidate revision where some member lives; forbid any model where a
member's picked version was not alive there. That is the entire
feasibility theory.

Candidates are right endpoints only — of a run, or of a tracked era.
The reduction is sound because every objective either counts something
constant across a run-and-era segment (distinct revisions, picked ranks,
mixed eras) or pushes a group rightward (freshest builds): whatever an
interior revision achieves, the right edge of its segment achieves too.
Any set of picks that coexists somewhere coexists at the smallest of
their runs' right endpoints, which is itself a candidate — so no model
is lost, only interchangeable interior copies of one.

## The policy

Lexicographic, highest priority first:

```prolog
#minimize { 1@4, R : used(R) }.                    % fewest distinct revisions
#maximize { K@3, S : pick(S, V), allowed(S, V, K) }. % newest versions
#minimize { 1@2, L, K : usedlib(L, K) }.           % fewest mixed lib eras
#maximize { R@1, G : at(G, R) }.                   % freshest builds
```

`--one <attr>` appends a hard clause per attr instead of relying on
priority 2 — glibc included (`--one-glibc` is shorthand for
`--one glibc`). Priority 2 only bites in the relaxed re-solve that
explains an UNSAT; with the clauses in force every tracked attr sits in
one era anyway. A solve with no `--one glibc` leaves glibc out of the
theory entirely and reports the link-world minimum after the fact:

```prolog
:- usedlib("zstd", K1), usedlib("zstd", K2), K1 < K2.
```

## The two flavors of "no"

A spec no emission can serve (unknown attr, empty range, date clamp left
nothing) never reaches clingo; Python says why directly. An UNSAT solve is
explained afterwards: a coexistence pair whose allowed lifetimes have empty
intersection is found by interval analysis and reported with dates —

```
python3@3.8.* and postgresql@13.* never overlapped:
python3@3.8.* was last alive 2021-07-18 (r621),
postgresql@13.* first alive 2021-08-01 (r625)
```

— and a `--one` failure re-solves relaxed to show which versions the
plan would have had to mix. Exact-pin queries stay on multiverse's greedy
path in spirit: the same answers, and `tests/test_solve.py` keeps the two
solvers agreeing.

## Grounding discipline

Nothing in the encoding ranges over revisions: `cand/1` holds one atom
per run or era endpoint, so ground size is (allowed versions) x
(candidates), a few thousand atoms for a wide query against the real
1,541-revision index. That endpoint restriction is what keeps wide
ranges fast — grounding `R = Lo..Hi` over whole lifetimes made
`ffmpeg@4.* ripgrep@>=14 ^bat` cost 3.5 s of optimality proof (the
freshness objective's weights reach the tip offset); on endpoints the
same query solves in 13 ms with the identical optimum. The place to
stay careful is future dependency-closure facts, where variables over
the whole index would explode; the front-end controls the domain by
construction.
