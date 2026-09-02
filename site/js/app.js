// Wires the page: the query box with live token highlighting and
// autocomplete, the solve button, and the three result renderings (the
// CLI-shaped text plan, the plan graph, the lock file to copy).

import { allAttrs, versionsOf } from "./data.js";
import { planSVG } from "./graph.js";
import { ParseError, parseQuery, tokenize } from "./specs.js";
import { solve, warmup } from "./solve.js";

const input = document.getElementById("query");
const oneGlibc = document.getElementById("one-glibc");
const highlight = document.getElementById("highlight");
const dropdown = document.getElementById("suggest");
const results = document.getElementById("results");
const solveButton = document.getElementById("solve");

const esc = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// --- highlighting ---------------------------------------------------------

function renderHighlight() {
  const tokens = tokenize(input.value);
  highlight.innerHTML =
    tokens.map((t) => `<span class="tk-${t.kind}">${esc(t.text)}</span>`).join("") +
    "\n";
  highlight.scrollLeft = input.scrollLeft;
}

// --- autocomplete ---------------------------------------------------------

let suggestions = [];
let selected = -1;

// the word the caret sits in, and where the completable fragment starts
function currentFragment() {
  const upto = input.value.slice(0, input.selectionStart);
  const wordStart = upto.search(/\S+$/);
  if (wordStart === -1) return null;
  const word = upto.slice(wordStart);

  const at = word.indexOf("@");
  if (at === -1) {
    const caret = word.startsWith("^") ? 1 : 0;
    return { mode: "attr", attr: null, start: wordStart + caret, prefix: word.slice(caret) };
  }
  const attr = word.slice(word.startsWith("^") ? 1 : 0, at).replace(/^\^/, "");
  // the version fragment starts after the last range operator
  const range = word.slice(at + 1);
  const m = range.match(/(?:.*(?:\|\||,|\.\.|>=|<=|>|<|=))?([A-Za-z0-9._+*-]*)$/);
  const frag = m ? m[1] : "";
  return {
    mode: "version",
    attr,
    start: wordStart + word.length - frag.length,
    prefix: frag,
  };
}

async function refreshSuggestions() {
  const frag = currentFragment();
  if (!frag || (frag.mode === "attr" && frag.prefix.length < 2)) {
    hideSuggestions();
    return;
  }

  let pool;
  if (frag.mode === "attr") {
    const attrs = await allAttrs();
    pool = attrs.filter((a) => a.startsWith(frag.prefix));
  } else {
    pool = (await versionsOf(frag.attr)).filter((v) => v.startsWith(frag.prefix));
  }
  suggestions = pool.slice(0, 12).map((text) => ({ text, frag }));
  selected = -1;

  if (!suggestions.length) {
    hideSuggestions();
    return;
  }
  dropdown.innerHTML = suggestions
    .map(
      (s, i) =>
        `<li data-i="${i}"><span class="muted">${frag.mode === "version" ? "@" : ""}</span>${esc(s.text)}</li>`,
    )
    .join("");
  dropdown.hidden = false;
}

function hideSuggestions() {
  suggestions = [];
  selected = -1;
  dropdown.hidden = true;
}

function accept(i) {
  const { text, frag } = suggestions[i];
  const caret = input.selectionStart;
  input.value = input.value.slice(0, frag.start) + text + input.value.slice(caret);
  const pos = frag.start + text.length;
  input.setSelectionRange(pos, pos);
  input.focus();
  hideSuggestions();
  renderHighlight();
}

function moveSelection(delta) {
  if (!suggestions.length) return;
  selected = (selected + delta + suggestions.length) % suggestions.length;
  [...dropdown.children].forEach((li, i) =>
    li.classList.toggle("selected", i === selected),
  );
}

// --- solving and rendering ------------------------------------------------

function planText(plan) {
  const lines = [`${plan.revisions} revision${plan.revisions === 1 ? "" : "s"}`];
  for (const group of plan.groups) {
    lines.push(`  ${group.label}  (${group.date}, r${group.off})`);
    for (const pin of group.pins) lines.push(`    ${pin.attr} ${pin.version}`);
  }
  if (plan.glibcs.length) lines.push(`  glibc: ${plan.glibcs.join(", ")}`);
  return lines.join("\n");
}

function lockJSON(plan) {
  const pins = {};
  for (const group of plan.groups) {
    for (const pin of group.pins) {
      pins[pin.attr] = {
        rev: group.rev,
        label: group.label,
        version: pin.version,
        date: group.date,
      };
    }
  }
  return JSON.stringify({ version: 1, pins }, null, 2);
}

async function runSolve() {
  const query = input.value.trim();
  if (!query) return;

  const url = new URL(location);
  url.searchParams.set("q", query);
  if (oneGlibc.checked) url.searchParams.set("glibc", "1");
  else url.searchParams.delete("glibc");
  history.replaceState(null, "", url);

  let groups;
  try {
    groups = parseQuery(query);
  } catch (e) {
    if (!(e instanceof ParseError)) throw e;
    results.innerHTML = `<p class="error">${esc(e.message)}</p>`;
    return;
  }

  results.innerHTML = `<p class="muted">solving…</p>`;
  const started = performance.now();
  let plan;
  try {
    plan = await solve(groups, { oneGlibc: oneGlibc.checked });
  } catch (e) {
    results.innerHTML = `<p class="error">${esc(String(e.message ?? e))}</p>`;
    return;
  }
  const ms = Math.round(performance.now() - started);

  if (plan.result === "unsat") {
    results.innerHTML = `
      <pre class="plan-text unsat">unsatisfiable: ${esc(plan.why)}</pre>
      <p class="muted">solved in ${ms} ms, in your browser</p>`;
    return;
  }

  results.innerHTML = `
    <pre class="plan-text">${esc(planText(plan))}</pre>
    <div class="plan-graph">${planSVG(plan)}</div>
    <details>
      <summary>multiverse.lock — <code>grail lock '${esc(query)}'</code></summary>
      <pre class="plan-text">${esc(lockJSON(plan))}</pre>
    </details>
    <p class="muted">solved in ${ms} ms by clingo-wasm running
      <a href="https://github.com/fzakaria/grail/blob/main/asp/solve.lp">solve.lp</a>
      verbatim, in your browser</p>`;
}

// --- events ---------------------------------------------------------------

input.addEventListener("input", () => {
  renderHighlight();
  refreshSuggestions();
});
input.addEventListener("scroll", () => (highlight.scrollLeft = input.scrollLeft));
input.addEventListener("keydown", (e) => {
  if (!dropdown.hidden) {
    if (e.key === "ArrowDown") return e.preventDefault(), moveSelection(1);
    if (e.key === "ArrowUp") return e.preventDefault(), moveSelection(-1);
    if ((e.key === "Tab" || e.key === "Enter") && suggestions.length) {
      e.preventDefault();
      return accept(selected === -1 ? 0 : selected);
    }
    if (e.key === "Escape") return hideSuggestions();
  }
  if (e.key === "Enter") {
    e.preventDefault();
    hideSuggestions();
    runSolve();
  }
});
input.addEventListener("blur", () => setTimeout(hideSuggestions, 150));
dropdown.addEventListener("mousedown", (e) => {
  const li = e.target.closest("li[data-i]");
  if (li) {
    e.preventDefault();
    accept(Number(li.dataset.i));
  }
});
solveButton.addEventListener("click", runSolve);

// example anchors keep their href for copy/middle-click; a plain click
// solves in place instead of reloading
for (const chip of document.querySelectorAll("[data-example]")) {
  chip.addEventListener("click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    input.value = chip.dataset.example;
    renderHighlight();
    runSolve();
  });
}

oneGlibc.addEventListener("change", () => {
  if (input.value.trim()) runSolve();
});

// deep links: ?q=...&glibc=1 solves on load
const params = new URL(location).searchParams;
oneGlibc.checked = params.get("glibc") === "1";
const initial = params.get("q");
if (initial) {
  input.value = initial;
  renderHighlight();
  runSolve();
}
renderHighlight();
warmup();
allAttrs();

// The site build substitutes the derivation's own $out into STORE_PATH, so
// the footer names the store path serving the page — the family signature.
// A local checkout still carries the placeholder, and the line stays hidden.
const STORE_PATH = "__STORE_PATH__";
if (!STORE_PATH.startsWith("__")) {
  document.getElementById("store-path").textContent = STORE_PATH;
  document.getElementById("store").hidden = false;
}
