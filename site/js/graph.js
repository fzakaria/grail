// Draw a solved plan as SVG, in the same visual language as the blog
// figures and asp/viz.lp: pins as plain rounded boxes, each solved
// revision as an accent box carrying its date, arrows from pin to the
// revision that serves it. Laid out by hand — the graph is a forest of
// shallow stars, which needs no layout engine.

const FONT = '"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace';
const PAD_X = 12;
const NODE_H = 34;
const CHAR_W = 7.3; // 12px mono, close enough for sizing boxes
const GAP_X = 16; // between sibling pins
const GROUP_GAP = 36; // between revision clusters
const ROW_GAP = 56; // pins row -> revisions row

function nodeWidth(lines) {
  return Math.max(...lines.map((l) => l.length)) * CHAR_W + PAD_X * 2;
}

function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function box(x, y, w, h, lines, cls, href) {
  const text = lines
    .map(
      (line, i) =>
        `<text x="${x + w / 2}" y="${y + h / 2 + (i - (lines.length - 1) / 2) * 14 + 4}"
           text-anchor="middle">${esc(line)}</text>`,
    )
    .join("");
  const g = `<g class="${cls}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8"/>${text}</g>`;
  // a node that names something the multiverse can show links to it
  return href ? `<a href="${href}" target="_blank" rel="noopener">${g}</a>` : g;
}

const MV = "https://nixmultiverse.com/";
const pkgURL = (attr, version) =>
  `${MV}?pkg=${encodeURIComponent(attr)}&ver=${encodeURIComponent(version)}`;
const revURL = (rev12) => `${MV}?view=revisions&rev=${rev12}`;

export function planSVG(plan) {
  // measure each revision cluster: its pins side by side, itself below
  const clusters = plan.groups.map((group) => {
    const pins = group.pins.map((p) => {
      const label = `${p.attr} ${p.version}`;
      return { label, w: nodeWidth([label]), href: pkgURL(p.attr, p.version) };
    });
    const pinsW = pins.reduce((sum, p) => sum + p.w, 0) + GAP_X * (pins.length - 1);
    const revLines = [`r${group.off} · ${group.date}`];
    const revW = nodeWidth(revLines);
    return { group, pins, revLines, revW, w: Math.max(pinsW, revW) };
  });

  const totalW =
    clusters.reduce((sum, c) => sum + c.w, 0) + GROUP_GAP * (clusters.length - 1) + 8;
  const pinsH = Math.max(...clusters.map((c) => (c.pins.length ? NODE_H : 0)));
  const revH = NODE_H;
  // a third row when eras are known: one node per distinct (lib, version),
  // so a coherent plan draws every revision converging on one node per lib
  const hasEras = plan.groups.some((g) => g.libs?.length);
  const height = pinsH + ROW_GAP + revH + (hasEras ? ROW_GAP + NODE_H : 0) + 8;

  // a curved edge ending in an arrowhead at (x2, y2)
  const edge = (x1, y1, x2, y2) =>
    `<path class="edge" d="M ${x1} ${y1} C ${x1} ${y1 + 24},
       ${x2} ${y2 - 24}, ${x2} ${y2 - 5}" />
     <path class="edge arrow" d="M ${x2 - 4} ${y2 - 9} L ${x2} ${y2 - 1} L ${x2 + 4} ${y2 - 9} Z"/>`;

  let x = 4;
  const parts = [];
  const eraSources = new Map(); // "lib version" label -> [revision center x]
  for (const c of clusters) {
    const pinsW =
      c.pins.reduce((sum, p) => sum + p.w, 0) + GAP_X * (c.pins.length - 1);
    let px = x + (c.w - pinsW) / 2;
    const revX = x + (c.w - c.revW) / 2;
    const revY = pinsH + ROW_GAP;

    for (const pin of c.pins) {
      parts.push(box(px, 2, pin.w, NODE_H, [pin.label], "pin", pin.href));
      parts.push(edge(px + pin.w / 2, 2 + NODE_H, revX + c.revW / 2, revY));
      px += pin.w + GAP_X;
    }
    parts.push(
      box(revX, revY, c.revW, revH, c.revLines, "rev", revURL(c.group.rev)),
    );
    // every era-tracked lib (glibc, plus --one attrs) becomes a node in
    // the third row; a coherent plan converges on one node per lib
    for (const [lib, version] of c.group.libs ?? []) {
      const key = `${lib} ${version}`;
      if (!eraSources.has(key)) eraSources.set(key, []);
      eraSources.get(key).push(revX + c.revW / 2);
    }
    x += c.w + GROUP_GAP;
  }

  // one node per distinct (lib, version), centered under the revisions it
  // serves and nudged right when neighbors would overlap
  const eraY = pinsH + ROW_GAP + revH + ROW_GAP;
  let lastRight = -Infinity;
  for (const [label, sources] of eraSources) {
    const w = nodeWidth([label]);
    let ex = sources.reduce((sum, s) => sum + s, 0) / sources.length - w / 2;
    ex = Math.max(ex, lastRight + GAP_X, 4);
    lastRight = ex + w;
    for (const s of sources)
      parts.push(edge(s, pinsH + ROW_GAP + revH, ex + w / 2, eraY));
    const [lib, version] = label.split(" ");
    parts.push(box(ex, eraY, w, NODE_H, [label], "lib", pkgURL(lib, version)));
  }

  // the era row can outgrow the clusters when nodes nudge right
  const finalW = Math.max(totalW, lastRight + 4);
  return `<svg class="plan" viewBox="0 0 ${finalW} ${height}"
    style="max-width:${finalW}px" font-family='${FONT}' font-size="12"
    role="img" aria-label="the solved plan">${parts.join("")}</svg>`;
}
