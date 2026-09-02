% The clingraph visualization encoding: how a solved plan becomes a
% picture. grail/viz.py emits the plan as facts with labels precomposed —
%
%   revnode(G, "r852 · 2022-09-12 · glibc 2.35").
%   pinnode(P, G, "python3 3.10.6").
%
% and the rules below turn them into graph atoms. The palette matches the
% blog figures; tokenize_svg.py maps these exact hexes onto site tokens.

graph(default).
attr(graph, default, rankdir, "TB").
attr(graph, default, bgcolor, "transparent").
attr(graph, default, nodesep, "0.35").
attr(graph, default, ranksep, "0.4").

attr(graph_nodes, default, fontname, "JetBrains Mono").
attr(graph_nodes, default, fontsize, "11").
attr(graph_nodes, default, shape, "box").
attr(graph_nodes, default, style, "rounded,filled").
attr(graph_edges, default, color, "#7d7970").
attr(graph_edges, default, arrowsize, "0.7").

% one node per picked pin, plain
node(pin(P)) :- pinnode(P, _, _).
attr(node, pin(P), label, L) :- pinnode(P, _, L).
attr(node, pin(P), fillcolor, "#fcfcfb") :- pinnode(P, _, _).
attr(node, pin(P), color, "#b5b1a9") :- pinnode(P, _, _).
attr(node, pin(P), fontcolor, "#0b0b0b") :- pinnode(P, _, _).

% one node per solved revision, in the accent style the plan node wears
% in the pipeline figure
node(rev(G)) :- revnode(G, _).
attr(node, rev(G), label, L) :- revnode(G, L).
attr(node, rev(G), fillcolor, "#fdeee6") :- revnode(G, _).
attr(node, rev(G), color, "#cf5d28") :- revnode(G, _).
attr(node, rev(G), fontcolor, "#0b0b0b") :- revnode(G, _).

% every pin hangs off the revision that serves it
edge((pin(P), rev(G))) :- pinnode(P, G, _).
