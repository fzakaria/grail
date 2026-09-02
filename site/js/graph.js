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

function box(x, y, w, h, lines, cls) {
  const text = lines
    .map(
      (line, i) =>
        `<text x="${x + w / 2}" y="${y + h / 2 + (i - (lines.length - 1) / 2) * 14 + 4}"
           text-anchor="middle">${esc(line)}</text>`,
    )
    .join("");
  return `<g class="${cls}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8"/>${text}</g>`;
}

export function planSVG(plan) {
  // measure each revision cluster: its pins side by side, itself below
  const clusters = plan.groups.map((group) => {
    const pins = group.pins.map((p) => {
      const label = `${p.attr} ${p.version}`;
      return { label, w: nodeWidth([label]) };
    });
    const pinsW = pins.reduce((sum, p) => sum + p.w, 0) + GAP_X * (pins.length - 1);
    const revLines = [`r${group.off} · ${group.date}`];
    const revW = nodeWidth(revLines);
    return { group, pins, revLines, revW, w: Math.max(pinsW, revW) };
  });

  const totalW =
    clusters.reduce((sum, c) => sum + c.w, 0) + GROUP_GAP * (clusters.length - 1) + 8;
  const pinsH = Math.max(...clusters.map((c) => (c.pins.length ? NODE_H : 0)));
  const height = pinsH + ROW_GAP + NODE_H + 8;

  let x = 4;
  const parts = [];
  for (const c of clusters) {
    const pinsW =
      c.pins.reduce((sum, p) => sum + p.w, 0) + GAP_X * (c.pins.length - 1);
    let px = x + (c.w - pinsW) / 2;
    const revX = x + (c.w - c.revW) / 2;
    const revY = pinsH + ROW_GAP;

    for (const pin of c.pins) {
      parts.push(box(px, 2, pin.w, NODE_H, [pin.label], "pin"));
      // arrow from pin bottom-center to revision top
      const x1 = px + pin.w / 2;
      const x2 = revX + c.revW / 2;
      parts.push(
        `<path class="edge" d="M ${x1} ${2 + NODE_H} C ${x1} ${2 + NODE_H + 24},
           ${x2} ${revY - 24}, ${x2} ${revY - 5}" />
         <path class="edge arrow" d="M ${x2 - 4} ${revY - 9} L ${x2} ${revY - 1} L ${x2 + 4} ${revY - 9} Z"/>`,
      );
      px += pin.w + GAP_X;
    }
    parts.push(box(revX, revY, c.revW, NODE_H, c.revLines, "rev"));
    x += c.w + GROUP_GAP;
  }

  return `<svg class="plan" viewBox="0 0 ${totalW} ${height}"
    style="max-width:${totalW}px" font-family='${FONT}' font-size="12"
    role="img" aria-label="the solved plan">${parts.join("")}</svg>`;
}
