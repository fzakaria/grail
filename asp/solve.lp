% grail's whole solver. Facts arrive from grail/facts.py:
%
%   spec(S).                 one per requested spec, S = s0, s1, ...
%   attrname(S, "python3").  names the id for humans; no rule reads it
%   group(G, S).             coexistence group membership (G = g0, g1, ...)
%   allowed(S, V, K).        version V passes S's range; K is its rank in
%                            compareVersions order (bigger = newer)
%   run(S, V, Lo, Hi).       one lifetime run of V, clamped to any date bounds
%   libera(L, K, Lo, Hi).    version-era K of library L reigns over Lo..Hi;
%                            emitted only for --one attrs, each of which
%                            also appends the hard no-mixing clause
%                            (facts.py one_rule) after these rules
%
% A model picks one version per spec and one revision per group such that
% every member's picked version was alive at the group's revision.

% choose exactly one version per spec
1 { pick(S, V) : allowed(S, V, _) } 1 :- spec(S).

% Candidate revisions are right endpoints only: of a lifetime run, or
% of a tracked era. Every objective either counts something constant
% across a run-and-era segment (distinct revisions, picked ranks, mixed
% eras) or pushes a group's revision rightward (freshest builds), so an
% interior revision is never strictly better than its segment's right
% edge. Grounding shrinks from the sum of run lengths to #runs + #eras
% candidates — milliseconds instead of seconds on wide ranges.
cand(R) :- run(_, _, _, R).
cand(R) :- libera(_, _, _, R).

% a group can sit at any candidate where some member version is alive;
% the constraint below narrows that to "every member version"
possible(G, R) :- group(G, S), run(S, V, Lo, Hi), cand(R), Lo <= R, R <= Hi.
1 { at(G, R) : possible(G, R) } 1 :- group(G, _).

alive(S, V, R) :- allowed(S, V, _), run(S, V, Lo, Hi), cand(R), Lo <= R, R <= Hi.
:- at(G, R), group(G, S), pick(S, V), not alive(S, V, R).

used(R) :- at(_, R).
usedlib(L, K) :- used(R), libera(L, K, Lo, Hi), Lo <= R, R <= Hi.

% the policy, lexicographic from the top:
%   fewest distinct revisions, then newest versions, then fewest mixed
%   eras of the --one attrs, then freshest builds. With the hard clauses
%   in force each --one attr sits in one era anyway; the era level only
%   bites in the relaxed re-solve that explains an UNSAT (solve.py drops
%   the hard clauses and asks for the least-mixed plan to name).
#minimize { 1@4, R : used(R) }.
#maximize { K@3, S : pick(S, V), allowed(S, V, K) }.
#minimize { 1@2, L, K : usedlib(L, K) }.
#maximize { R@1, G : at(G, R) }.

#show pick/2.
#show at/2.
