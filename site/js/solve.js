// The browser solve: resolve specs against the shards, emit the same facts
// grail/facts.py emits, run the repo's solve.lp VERBATIM through
// clingo-wasm, and turn the optimum model into a plan — or explain why
// there is none, with the same interval analysis the CLI uses.

import clingo from "clingo-wasm";
import { closeRuns, glibcEras, historyOf, revisions } from "./data.js";
import { compare, components } from "./versions.js";
import { specMatches } from "./specs.js";

let solveLpPromise;
function solveLp() {
  // resolved against this module's own URL: the site build copies
  // solve.lp into the content-hashed js.<hash>/ tree, so the fetched
  // encoding always matches the module that fetched it. Serving a raw
  // checkout will 404 here — `nix run .#serve` (the built tree) is the
  // dev flow.
  solveLpPromise ??= fetch(new URL("solve.lp", import.meta.url)).then((r) =>
    r.text(),
  );
  return solveLpPromise;
}

const q = (s) => `"${s.replaceAll('"', '\\"')}"`;

// specs resolved against the index: which versions survive each range
async function resolveSpecs(groups, tip) {
  const resolved = [];
  const problems = [];

  let sid = 0;
  for (let g = 0; g < groups.length; g += 1) {
    for (const spec of groups[g]) {
      const entry = {
        sid: `s${sid}`,
        gid: `g${g}`,
        spec,
        versions: new Map(), // version -> {rank, runs}
      };
      sid += 1;

      const history = await historyOf(spec.attr);
      if (history === null) {
        problems.push(`${spec.attr} is not in the index`);
        continue;
      }
      const ranked = Object.keys(history).sort(compare);
      ranked.forEach((version, rank) => {
        if (!specMatches(spec, version)) return;
        entry.versions.set(version, {
          rank,
          runs: closeRuns(history[version], tip),
        });
      });
      if (!entry.versions.size) {
        problems.push(`no version of ${spec.attr} matches the range`);
        continue;
      }
      resolved.push(entry);
    }
  }
  return { resolved, problems };
}

function emitFacts(resolved, eras) {
  const lines = [];
  for (const sf of resolved) {
    lines.push(`spec(${sf.sid}).`);
    lines.push(`attrname(${sf.sid}, ${q(sf.spec.attr)}).`);
    lines.push(`group(${sf.gid}, ${sf.sid}).`);
    for (const [version, { rank, runs }] of sf.versions) {
      lines.push(`allowed(${sf.sid}, ${q(version)}, ${rank}).`);
      for (const [lo, hi] of runs) lines.push(`run(${sf.sid}, ${q(version)}, ${lo}, ${hi}).`);
    }
  }
  eras.forEach(([, lo, hi], k) => lines.push(`glibcera(${k}, ${lo}, ${hi}).`));
  return lines.join("\n");
}

// merged sorted union of one spec's allowed runs, for unsat explanations
function specUnion(sf) {
  const runs = [...sf.versions.values()].flatMap((v) => v.runs).sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const [lo, hi] of runs) {
    const last = merged[merged.length - 1];
    if (last && lo <= last[1] + 1) last[1] = Math.max(last[1], hi);
    else merged.push([lo, hi]);
  }
  return merged;
}

function describe(sf) {
  if (sf.versions.size === 1) return `${sf.spec.attr} ${sf.versions.keys().next().value}`;
  return sf.spec.text || sf.spec.attr;
}

function neverOverlapped(resolved, revs) {
  const byGroup = new Map();
  for (const sf of resolved) {
    if (!byGroup.has(sf.gid)) byGroup.set(sf.gid, []);
    byGroup.get(sf.gid).push(sf);
  }
  for (const members of byGroup.values()) {
    for (let i = 0; i < members.length; i += 1) {
      for (let j = i + 1; j < members.length; j += 1) {
        let a = members[i];
        let b = members[j];
        let ua = specUnion(a);
        let ub = specUnion(b);
        const overlap = ua.some(([lo1, hi1]) => ub.some(([lo2, hi2]) => lo1 <= hi2 && lo2 <= hi1));
        if (overlap) continue;
        if (ua[ua.length - 1][1] > ub[ub.length - 1][1]) {
          [a, b, ua, ub] = [b, a, ub, ua];
        }
        const last = ua[ua.length - 1][1];
        const first = ub[0][0];
        return (
          `${describe(a)} and ${describe(b)} never overlapped: ` +
          `${describe(a)} was last alive ${revs[last][0]} (r${last}), ` +
          `${describe(b)} first alive ${revs[first][0]} (r${first})`
        );
      }
    }
  }
  return null;
}

// the hard clause --one-glibc appends, same text as grail/facts.py
const ONE_GLIBC_RULE = ":- usedglibc(K1), usedglibc(K2), K1 < K2.\n";

// 0 = compute ALL models, so the search runs to the proven optimum and the
// last witness is it; the default of one model returns the first found
async function runClingo(program) {
  const answer = await clingo.run(program, 0);
  if (answer.Result === "ERROR") throw new Error(answer.Error ?? "clingo failed");
  return answer;
}

export async function solve(groups, { oneGlibc = false } = {}) {
  const revs = await revisions();
  const tip = revs.length - 1;
  const eras = await glibcEras(tip);

  const { resolved, problems } = await resolveSpecs(groups, tip);
  if (problems.length) return { result: "unsat", why: problems.join("; ") };

  const base = emitFacts(resolved, eras) + "\n" + (await solveLp());
  const program = base + (oneGlibc ? ONE_GLIBC_RULE : "");
  const answer = await runClingo(program);

  let witnesses = answer.Call?.[0]?.Witnesses;
  if (answer.Result === "UNSATISFIABLE" || !witnesses?.length) {
    let why = neverOverlapped(resolved, revs);
    if (why === null && oneGlibc) {
      // relax the glibc clause; if that solves, the eras were the problem
      const relaxed = await runClingo(base);
      const relaxedWitnesses = relaxed.Call?.[0]?.Witnesses;
      if (relaxedWitnesses?.length) {
        const atoms = relaxedWitnesses[relaxedWitnesses.length - 1].Value;
        const offsets = atoms
          .map((a) => a.match(/^at\(g\d+,(\d+)\)$/))
          .filter(Boolean)
          .map((m) => Number(m[1]));
        const mixed = eras
          .filter(([, lo, hi]) => offsets.some((off) => lo <= off && off <= hi))
          .map(([version]) => version);
        why = `satisfiable only by mixing glibc eras (${[...new Set(mixed)].join(", ")}); one-glibc forbids that`;
      }
    }
    return { result: "unsat", why: why ?? "no model satisfies the query" };
  }

  // the last witness is the optimum
  const atoms = witnesses[witnesses.length - 1].Value;
  const picked = new Map();
  const where = new Map();
  for (const atom of atoms) {
    let m = atom.match(/^pick\((s\d+),"((?:[^"\\]|\\.)*)"\)$/);
    if (m) picked.set(m[1], m[2].replaceAll('\\"', '"'));
    m = atom.match(/^at\((g\d+),(\d+)\)$/);
    if (m) where.set(m[1], Number(m[2]));
  }

  const groupsOut = new Map();
  for (const sf of resolved) {
    const off = where.get(sf.gid);
    if (!groupsOut.has(sf.gid)) {
      const [date, rev12] = revs[off];
      const era = eras.find(([, lo, hi]) => lo <= off && off <= hi);
      groupsOut.set(sf.gid, {
        off,
        date,
        rev: rev12,
        label: `${date}-${rev12}`,
        glibc: era ? era[0] : null,
        pins: [],
      });
    }
    groupsOut.get(sf.gid).pins.push({ attr: sf.spec.attr, version: picked.get(sf.sid) });
  }

  const plan = [...groupsOut.values()].sort((a, b) => a.off - b.off);
  const offsets = [...new Set(plan.map((g) => g.off))];
  const glibcs = eras
    .filter(([, lo, hi]) => offsets.some((off) => lo <= off && off <= hi))
    .map(([version]) => version);

  return {
    result: "sat",
    revisions: offsets.length,
    groups: plan,
    glibcs: [...new Set(glibcs)],
  };
}

// touches nothing heavy; app.js calls it at load so the first solve is warm
export function warmup() {
  solveLp();
  clingo.run("a.").catch(() => {});
}

export { components };
