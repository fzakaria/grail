// Nix's builtins.compareVersions, ported byte-for-byte from grail's Python
// port of names.cc (which tests/test_versions.py holds against real nix).
// The quirks are load-bearing: only "pre" sorts before its release, an
// empty component is below a number but above nothing else, letters sort
// below numbers.

const SEPARATORS = new Set([".", "-"]);
const PRE = "pre";

export function components(version) {
  const parts = [];
  let i = 0;
  const n = version.length;
  const isDigit = (c) => c >= "0" && c <= "9";
  while (i < n) {
    if (SEPARATORS.has(version[i])) {
      i += 1;
      continue;
    }
    const start = i;
    if (isDigit(version[i])) {
      while (i < n && isDigit(version[i])) i += 1;
    } else {
      while (i < n && !isDigit(version[i]) && !SEPARATORS.has(version[i])) i += 1;
    }
    parts.push(version.slice(start, i));
  }
  return parts;
}

function componentLess(a, b) {
  const aNum = /^[0-9]+$/.test(a) ? BigInt(a) : null;
  const bNum = /^[0-9]+$/.test(b) ? BigInt(b) : null;
  if (aNum !== null && bNum !== null) return aNum < bNum;
  if (a === "" && bNum !== null) return true;
  if (a === PRE && b !== PRE) return true;
  if (b === PRE) return false;
  if (bNum !== null) return true;
  if (aNum !== null) return false;
  return a < b;
}

export function compare(a, b) {
  const ca = components(a);
  const cb = components(b);
  const len = Math.max(ca.length, cb.length);
  for (let i = 0; i < len; i += 1) {
    const x = i < ca.length ? ca[i] : "";
    const y = i < cb.length ? cb[i] : "";
    if (x === y) continue;
    if (componentLess(x, y)) return -1;
    if (componentLess(y, x)) return 1;
  }
  return 0;
}

// component-wise prefix: 3.8 accepts 3.8.9 and 3.8, refuses 3.81
export function isPrefix(pattern, candidate) {
  const p = components(pattern);
  const c = components(candidate);
  if (p.length > c.length) return false;
  return p.every((part, i) => part === c[i]);
}
