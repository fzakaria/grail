% grail's whole solver. Facts arrive from grail/facts.py:
%
%   spec(S).                 one per requested spec, S = s0, s1, ...
%   group(G, S).             coexistence group membership (G = g0, g1, ...)
%   allowed(S, V, K).        version V passes S's range; K is its rank in
%                            compareVersions order (bigger = newer)
%   run(S, V, Lo, Hi).       one lifetime run of V, clamped to any date bounds
%   glibcera(K, Lo, Hi).     glibc era K reigns over revisions Lo..Hi
%
% A model picks one version per spec and one revision per group such that
% every member's picked version was alive at the group's revision.

% choose exactly one version per spec
1 { pick(S, V) : allowed(S, V, _) } 1 :- spec(S).

% a group can sit at any revision where some member version is alive;
% the constraint below narrows that to "every member version"
possible(G, R) :- group(G, S), run(S, V, Lo, Hi), R = Lo..Hi.
1 { at(G, R) : possible(G, R) } 1 :- group(G, _).

alive(S, V, R) :- allowed(S, V, _), run(S, V, Lo, Hi), R = Lo..Hi.
:- at(G, R), group(G, S), pick(S, V), not alive(S, V, R).

used(R) :- at(_, R).
usedglibc(K) :- used(R), glibcera(K, Lo, Hi), Lo <= R, R <= Hi.

% the policy, lexicographic from the top:
%   fewest distinct revisions, then newest versions, then fewest glibc
%   eras, then freshest builds
#minimize { 1@4, R : used(R) }.
#maximize { K@3, S : pick(S, V), allowed(S, V, K) }.
#minimize { 1@2, K : usedglibc(K) }.
#maximize { R@1, G : at(G, R) }.

#show pick/2.
#show at/2.
