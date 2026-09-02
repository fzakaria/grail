// The static data layer: attrs.json (autocomplete corpus), revisions.json
// (offset -> [date, rev12]), and history shards fetched on demand and
// cached. Everything is a same-origin file; there is no server.

import { compare } from "./versions.js";

let attrsPromise;
let revisionsPromise;
const shardCache = new Map();

export function shardOf(attr) {
  const key = attr.toLowerCase().slice(0, 2).padEnd(2, "_");
  return key.replace(/[^a-z0-9]/g, "_");
}

async function fetchJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export function allAttrs() {
  attrsPromise ??= fetchJSON("data/attrs.json");
  return attrsPromise;
}

export function revisions() {
  revisionsPromise ??= fetchJSON("data/revisions.json");
  return revisionsPromise;
}

async function shard(attr) {
  const key = shardOf(attr);
  if (!shardCache.has(key)) {
    shardCache.set(
      key,
      fetchJSON(`data/history/${key}.json`).catch(() => ({})),
    );
  }
  return shardCache.get(key);
}

// attr -> {version: runs} | null, runs left in index shape
export async function historyOf(attr) {
  const content = await shard(attr);
  return content[attr] ?? null;
}

// runs normalized to closed [lo, hi] pairs, the open tip resolved
export function closeRuns(raw, tip) {
  const runs = Array.isArray(raw[0]) ? raw : [raw];
  return runs.map(([lo, hi]) => [lo, hi === null ? tip : hi]);
}

// every version of an attr, newest first — the version autocomplete
export async function versionsOf(attr) {
  const history = await historyOf(attr);
  if (!history) return [];
  return Object.keys(history).sort((a, b) => compare(b, a));
}

// glibc's lifetime runs as [version, lo, hi] eras sorted by lo
export async function glibcEras(tip) {
  const history = await historyOf("glibc");
  if (!history) return [];
  const eras = [];
  for (const [version, raw] of Object.entries(history)) {
    for (const [lo, hi] of closeRuns(raw, tip)) eras.push([version, lo, hi]);
  }
  eras.sort((a, b) => a[1] - b[1]);
  return eras;
}
