// The browser solve: resolve specs against the shards, emit the same facts
// grail/facts.py emits, run the repo's solve.lp VERBATIM through
// clingo-wasm, and turn the optimum model into a plan — or explain why
// there is none, with the same interval analysis the CLI uses.

import clingo from "clingo-wasm";
import { closeRuns, libEras, historyOf, revisions } from "./data.js";
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

function emitFacts(resolved, libs) {
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
  for (const [lib, eras] of libs) {
    eras.forEach(([, lo, hi], k) =>
      lines.push(`libera(${q(lib)}, ${k}, ${lo}, ${hi}).`),
    );
  }
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
        // line breaks at the clause boundaries; the page shows the
        // message in a <pre>, so this reads like the CLI output
        return (
          `${describe(a)} and ${describe(b)} never overlapped:\n` +
          `${describe(a)} was last alive ${revs[last][0]} (r${last}),\n` +
          `${describe(b)} first alive ${revs[first][0]} (r${first})`
        );
      }
    }
  }
  return null;
}

// the hard clause --one <attr> appends, same text as grail/facts.py
const oneRule = (lib) =>
  `:- usedlib(${q(lib)}, K1), usedlib(${q(lib)}, K2), K1 < K2.\n`;

// 0 = compute ALL models, so the search runs to the proven optimum and the
// last witness is it; the default of one model returns the first found
async function runClingo(program) {
  const answer = await clingo.run(program, 0);
  if (answer.Result === "ERROR") throw new Error(answer.Error ?? "clingo failed");
  return answer;
}

// versions of one era-tracked lib that the offsets fall in, era order
function libVersions(offsets, eras) {
  const names = [];
  for (const [version, lo, hi] of eras) {
    if (!names.includes(version) && offsets.some((o) => lo <= o && o <= hi))
      names.push(version);
  }
  return names;
}

export async function solve(groups, { one = [] } = {}) {
  const revs = await revisions();
  const tip = revs.length - 1;

  // --one attrs become solver facts, and every one of them gets the
  // hard no-mixing clause — glibc included when asked. An unconstrained
  // solve leaves glibc alone and just reports the newest spanned era
  // (symbol versioning makes that the link-world answer).
  const constrained = [...new Set(one)];
  const hard = constrained;
  const libs = [];
  for (const lib of constrained) {
    const eras = await libEras(lib, tip);
    if (!eras.length)
      return { result: "unsat", why: `--one ${lib}: not in the index` };
    libs.push([lib, eras]);
  }
  // glibc eras are always fetched for the report and the graph row
  const glibcEras = await libEras("glibc", tip);
  const display = [["glibc", glibcEras], ...libs.filter(([l]) => l !== "glibc")];

  const { resolved, problems } = await resolveSpecs(groups, tip);
  if (problems.length) return { result: "unsat", why: problems.join("; ") };

  const base = emitFacts(resolved, libs) + "\n" + (await solveLp());
  const program = base + hard.map(oneRule).join("");
  const answer = await runClingo(program);

  let witnesses = answer.Call?.[0]?.Witnesses;
  if (answer.Result === "UNSATISFIABLE" || !witnesses?.length) {
    let why = neverOverlapped(resolved, revs);
    if (why === null && hard.length) {
      // relax the no-mixing clauses; if that solves, name what mixed
      const relaxed = await runClingo(base);
      const relaxedWitnesses = relaxed.Call?.[0]?.Witnesses;
      if (relaxedWitnesses?.length) {
        const atoms = relaxedWitnesses[relaxedWitnesses.length - 1].Value;
        const offsets = atoms
          .map((a) => a.match(/^at\(g\d+,(\d+)\)$/))
          .filter(Boolean)
          .map((m) => Number(m[1]));
        const mixed = libs
          .filter(([lib]) => hard.includes(lib))
          .map(([lib, eras]) => [lib, libVersions(offsets, eras)])
          .filter(([, versions]) => versions.length > 1)
          .map(([lib, versions]) => `${lib} ${versions.join("/")}`);
        if (mixed.length)
          why =
            `satisfiable only by mixing ${mixed.join(", ")};\n` +
            `keeping one version of each forbids that`;
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
      // one entry per tracked lib whose era covers this revision
      const revLibs = display
        .map(([lib, eras]) => {
          const era = eras.find(([, lo, hi]) => lo <= off && off <= hi);
          return era ? [lib, era[0]] : null;
        })
        .filter(Boolean);
      groupsOut.set(sf.gid, {
        off,
        date,
        rev: rev12,
        label: `${date}-${rev12}`,
        glibc: Object.fromEntries(revLibs).glibc ?? null,
        libs: revLibs,
        pins: [],
      });
    }
    groupsOut.get(sf.gid).pins.push({ attr: sf.spec.attr, version: picked.get(sf.sid) });
  }

  const plan = [...groupsOut.values()].sort((a, b) => a.off - b.off);
  const offsets = [...new Set(plan.map((g) => g.off))];
  const planLibs = display.map(([lib, eras]) => [lib, libVersions(offsets, eras)]);
  const glibcs = Object.fromEntries(planLibs).glibc ?? [];

  return {
    result: "sat",
    revisions: offsets.length,
    groups: plan,
    glibcs,
    glibcRequired: glibcs[glibcs.length - 1] ?? null,
    libs: planLibs,
  };
}

// touches nothing heavy; app.js calls it at load so the first solve is warm
export function warmup() {
  solveLp();
  clingo.run("a.").catch(() => {});
}

export { components };
