# glibc, coexistence, and the ELF fact tiers

## Why coexistence is the safe default

Running packages from different revisions side by side is what multiverse
does all day: each closure is self-contained, so a 2015 python and a 2026
ripgrep never meet. Building one derivation from mixed revisions is
different, because inputs get linked into one process image, and Nix
RPATH-pins every library to its own glibc. Mix revisions carelessly and the
dynamic linker can walk one library's RUNPATH to an old `libc.so.6` while
the executable's `PT_INTERP` names a new one — two libcs in one process,
the classic mixed-nixpkgs failure.

A coexistence group dodges the whole question by construction: one
revision, one glibc, one compiler. `grail.lib.mkDerivation` takes its
stdenv from the solved revision, so the build world is time-consistent.

The real invariant is sharper than "one revision", though: it is one glibc
per linked process image, and glibc is backward compatible through symbol
versioning. An object that demands at most `GLIBC_2.27` symbols links and
runs fine against glibc 2.38. Same for `GLIBCXX_*`/`CXXABI_*` from
libstdc++. That compatibility is directional — newer glibc satisfies older
demands, never the reverse — which is what the fact tiers exploit.

Spack solves the forward version of this problem in its own ASP encoding
(`libc_compatibility.lp`: a reused binary must be compatible with the host
libc). grail's version points backward through history instead.

## Tier 0 — metadata only, implemented

`glibc` is an indexed attr, so its lifetime runs already say which glibc
reigned at every revision. Those become `libera` facts under
`--one glibc` (shorthand: `--one-glibc`), and mixing eras is then a hard
error like any other `--one` attr. No ELF bytes involved.

The other zero-cost fact source is narinfo `References`: a store path's
closure lists the exact glibc it was linked against, and the multiverse
census already crawls narinfos. `linked_against(path, glibc-2.35)` costs
nothing new to produce.

## Tier 1 — precise demands, prototyped

`tools/elf-facts.py` reads an ELF and emits the demand side as facts:

- `needs("libssl.so.1.1").` — `DT_NEEDED` sonames: which deps are
  ABI-bearing at all, and whether a second libc is being dragged in
- `verneed("libc.so.6", "GLIBC_2.27").` — `.gnu.version_r`: the exact
  version-set demands per needed soname
- `runpath(...)` / `interp(...)` — where a second glibc would sneak from,
  and which loader runs the image

Is verneed the whole story? For glibc and libstdc++ mixing, essentially
yes: verneed carries the demands and symbol versioning is the contract. The
companions above matter for detection and mechanism. Mixing arbitrary
libraries across revisions (curl from world A against openssl from world B)
additionally needs export/import matching — undefined dynsyms on one side
against `.gnu.version_d` definitions on the other. And one thing no symbol
table shows: a struct layout change under an unbumped soname is invisible
to all of this. Symbol presence is not ABI; the tiers narrow the risk, they
do not abolish it.

The economics: these facts are properties of immutable store paths, so the
cache is append-only and each path is analyzed at most once, ever. NARs
stream files in order, so verneed for a library costs a streamed prefix —
megabytes — not the closure, and never the corpus.

## Tier 2 — refine on demand, designed

Do not sweep 307k package-versions. Solve with tier-0 facts; when the
answer is UNSAT, or wants to cross a revision boundary the coarse facts
cannot justify, fetch precise facts for exactly the candidate paths on that
frontier, add them, re-solve. clingo's multi-shot API exists for precisely
this add-facts-and-continue loop. Every refined fact lands in the immutable
cache, so the corpus densifies along the paths people actually query.

## Beyond glibc — `--one <attr>`

The era constraint generalizes to any attr: `--one zstd --one openssl`
demands that every chosen revision ship the same version of zstd and of
openssl. The data is the same lifetime index glibc uses — which version of
the attr each revision shipped — so no closure analysis is needed.

glibc gets the same hard clause when asked: `--one glibc` (shorthand:
`--one-glibc`) means one era or unsat, exactly like `--one zstd`. What is
special about glibc is the _default_. Its symbol versioning makes
compatibility directional — a newer glibc satisfies every older demand,
and under tier-0 facts an input never demands more than the glibc of the
revision it was built in — so an unconstrained solve needs no glibc
clause at all: every plan reports the minimum a shared link world must
run (`glibc: 2.37 serves every input (eras spanned: 2.34, 2.37)`).

Note what that report leans on: the directional contract holds only once
exactly one `libc.so.6` is loaded and it is the newest. Nix RPATH-pinning
can defeat that arrangement (the two-libc loader hazard above), and
`--one glibc` is the way to refuse plans that depend on it — one era, one
glibc store version, nothing for the loader to get wrong.

The constraint the directional contract _would_ justify — pick one glibc
G and require every input's supported range to contain G — is not worth
encoding at tier 0: every range is `[build era, ∞)` (glibc does not
remove the symbols these packages demand), so the intersection is never
empty and the constraint can never fail. It becomes real at tier 1, where
verneed facts and symbol-removal data put upper bounds on ranges; only
then can "no single glibc serves these inputs" come back as an unsat.

What it guarantees: version-level ABI agreement. The scenario it exists
for is real and has happened in nixpkgs: an app vendors one zstd while
libsystemd dlopens another, the two disagree on struct layout, and logging
corrupts the address space. `--one zstd` makes any plan that ships two
zstd versions unsatisfiable, and the solver names what would have mixed:

```console
$ grail solve 'ffmpeg@5.* nodejs@16.*' --one zstd --one openssl
unsatisfiable: satisfiable only by mixing zstd 1.5.2/1.5.5,
openssl 1.1.1q/3.0.10; --one forbids that
```

What it deliberately does not guarantee: one store path. Two revisions can
ship the same zstd version as different rebuilds; agreeing on the version
is the ABI contract, agreeing on the path needs one revision — that is
what a `^` coexistence group is for. And no link-level constraint sees
API-level mixing: an object created by one library version handed to
another resolves its symbols fine and corrupts its fields anyway.
