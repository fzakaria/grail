// The query grammar, twice over: tokenize() classifies every character span
// for the live syntax highlighting, and parseQuery() builds the same AST
// grail/specs.py builds (docs/grammar.md is normative for both).

import { compare, isPrefix } from "./versions.js";

const COMPARATORS = [">=", "<=", ">", "<", "="];
const ATTR_RE = /^[A-Za-z0-9_+-]+(\.[A-Za-z0-9_+-]+)*$/;
const VERSION_RE = /^[A-Za-z0-9._+-]+$/;

export class ParseError extends Error {}

// --- tokenizer, for highlighting -----------------------------------------
// Returns [{text, kind}] covering the input exactly. Kinds: ws, caret,
// attr, at, cmp, version, dots, comma, pipes, error.
export function tokenize(text) {
  const out = [];
  const push = (t, kind) => t && out.push({ text: t, kind });

  for (const piece of text.split(/(\s+)/)) {
    if (!piece) continue;
    if (/^\s+$/.test(piece)) {
      push(piece, "ws");
      continue;
    }

    let rest = piece;
    if (rest.startsWith("^")) {
      push("^", "caret");
      rest = rest.slice(1);
    }
    const at = rest.indexOf("@");
    const attr = at === -1 ? rest : rest.slice(0, at);
    push(attr, ATTR_RE.test(attr) ? "attr" : "error");
    if (at === -1) continue;
    push("@", "at");

    // walk the range, splitting on the operators the grammar knows
    let range = rest.slice(at + 1);
    while (range.length) {
      const op = COMPARATORS.find((c) => range.startsWith(c));
      if (op) {
        push(op, "cmp");
        range = range.slice(op.length);
        continue;
      }
      if (range.startsWith("..")) {
        push("..", "dots");
        range = range.slice(2);
        continue;
      }
      if (range.startsWith("||")) {
        push("||", "pipes");
        range = range.slice(2);
        continue;
      }
      if (range.startsWith(",")) {
        push(",", "comma");
        range = range.slice(1);
        continue;
      }
      const m = range.match(/^[A-Za-z0-9._+*-]+?(?=\.\.|\|\||,|$)/);
      if (!m) {
        push(range, "error");
        break;
      }
      push(m[0], VERSION_RE.test(m[0].replace(/\*$/, "x")) ? "version" : "error");
      range = range.slice(m[0].length);
    }
  }
  return out;
}

// --- parser, mirroring grail/specs.py ------------------------------------

function matchTerm(term, candidate) {
  switch (term.op) {
    case "prefix":
      return isPrefix(term.version, candidate);
    case "interval": {
      const below =
        compare(candidate, term.upper) <= 0 || isPrefix(term.upper, candidate);
      return compare(candidate, term.version) >= 0 && below;
    }
    default: {
      const c = compare(candidate, term.version);
      return { ">=": c >= 0, ">": c > 0, "<=": c <= 0, "<": c < 0, "=": c === 0 }[
        term.op
      ];
    }
  }
}

function parseTerm(text) {
  for (const cmp of COMPARATORS) {
    if (text.startsWith(cmp)) {
      const version = text.slice(cmp.length);
      if (!VERSION_RE.test(version))
        throw new ParseError(`comparator ${cmp} needs a version, got "${text}"`);
      return { op: cmp, version };
    }
  }
  if (text.includes("..")) {
    const [lo, hi] = text.split("..");
    if (!VERSION_RE.test(lo) || !VERSION_RE.test(hi))
      throw new ParseError(`interval needs both endpoints, got "${text}"`);
    return { op: "interval", version: lo, upper: hi };
  }
  let bare = text;
  for (const suffix of [".*", ".x"]) {
    if (bare.endsWith(suffix)) {
      bare = bare.slice(0, -suffix.length);
      break;
    }
  }
  if (!VERSION_RE.test(bare)) throw new ParseError(`malformed version term "${text}"`);
  return { op: "prefix", version: bare };
}

function parseRange(text) {
  const alts = text.split("||").map((alt) => {
    if (!alt) throw new ParseError(`empty alternative in range "${text}"`);
    return alt.split(",").map(parseTerm);
  });
  return {
    alts,
    matches: (candidate) =>
      alts.some((terms) => terms.every((t) => matchTerm(t, candidate))),
  };
}

function parseSpec(token) {
  const at = token.indexOf("@");
  const attr = at === -1 ? token : token.slice(0, at);
  if (!ATTR_RE.test(attr)) throw new ParseError(`malformed attribute name "${attr}"`);
  if (at === -1) return { attr, range: null, text: token };
  const rangeText = token.slice(at + 1);
  if (!rangeText) throw new ParseError(`"${attr}" has @ but no range`);
  return { attr, range: parseRange(rangeText), text: token };
}

export function parseQuery(text) {
  const tokens = text.split(/\s+/).filter(Boolean);
  if (!tokens.length) throw new ParseError("empty query");

  const groups = [];
  for (let token of tokens) {
    const chained = token.startsWith("^");
    if (chained) {
      token = token.slice(1);
      if (!token) throw new ParseError("dangling ^");
      if (!groups.length) throw new ParseError("^ must follow a spec to chain onto");
    }
    const spec = parseSpec(token);
    if (chained) groups[groups.length - 1].push(spec);
    else groups.push([spec]);
  }
  return groups;
}

export function specMatches(spec, version) {
  return spec.range === null || spec.range.matches(version);
}
