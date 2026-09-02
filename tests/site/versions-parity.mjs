// Holds the site's JS port of compareVersions against the Python port
// (itself held against real nix by tests/test_versions.py): the check
// derivation runs Python over tests/fixtures/version-pairs.json to produce
// expected signs, then this script asserts the JS agrees on every pair.
//
// Usage: node versions-parity.mjs <pairs.json> <expected.json> <versions.js>
import { readFileSync } from "node:fs";
import { exit, argv } from "node:process";

const [pairsFile, expectedFile, versionsModule] = argv.slice(2);
const pairs = JSON.parse(readFileSync(pairsFile, "utf8"));
const expected = JSON.parse(readFileSync(expectedFile, "utf8"));
const { compare } = await import(new URL(versionsModule, `file://${process.cwd()}/`));

let failures = 0;
pairs.forEach(([a, b], i) => {
  const got = Math.sign(compare(a, b));
  if (got !== expected[i]) {
    console.error(`MISMATCH compare(${JSON.stringify(a)}, ${JSON.stringify(b)}): js ${got}, python ${expected[i]}`);
    failures += 1;
  }
});

if (failures) {
  console.error(`${failures}/${pairs.length} pairs disagree`);
  exit(1);
}
console.log(`${pairs.length} pairs agree`);
