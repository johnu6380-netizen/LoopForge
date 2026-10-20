// Validates the exported replay data against the saved evidence.
// Run from the project root:  node web/scripts/validate-data.mjs
// Uses only Node built-ins. Never executes candidate code: it only re-derives
// tour validity, tour length, ratio and fitness from the stored points and tours.
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const DATA = join(here, "..", "public", "data");
const EVIDENCE = join(here, "..", "public", "evidence");

let checks = 0;
let failures = 0;
const warnings = [];
function ok(cond, msg) {
  checks++;
  if (!cond) {
    failures++;
    console.log("  FAIL: " + msg);
  }
}
const near = (a, b, tol = 1e-9) =>
  typeof a === "number" && typeof b === "number" && Math.abs(a - b) <= tol * Math.max(1, Math.abs(b));
const load = (rel) => JSON.parse(readFileSync(join(DATA, rel), "utf8"));
const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");

// Numbers copied from the finalize output and saved summary.json files.
const SEED = { dev: 1.1524026807290622, test: 1.150388660386074 };
const EXPECTED = {
  "gpt-01": {
    statuses: ["valid", "valid", "valid", "invalid", "valid", "valid", "valid"],
    counts: { proposals: 6, valid: 5, invalid: 1, duplicate: 0, improvements: 1 },
    best: "p0001", dev: 0.977214463501943, test: 0.9513471808173168,
  },
  "claude-01": {
    statuses: ["valid", "valid", "valid", "valid", "valid", "valid", "valid"],
    counts: { proposals: 6, valid: 6, invalid: 0, duplicate: 0, improvements: 2 },
    best: "p0002", dev: 0.9705716373348318, test: 0.9439828265428228,
  },
};

function checkEval(label, ev, instSet, refs) {
  if (!ev) return;
  const rows = ev.instances || [];
  rows.forEach((r, i) => {
    const tag = `${label} instance ${i}`;
    if (!r.valid) {
      ok(r.tour == null, `${tag}: invalid instance should have no tour`);
      return;
    }
    const pts = instSet.instances[i] && instSet.instances[i].points;
    if (!ok(!!pts, `${tag}: no points for this instance`) && !pts) return;
    ok(r.n === pts.length, `${tag}: n mismatch`);
    const t = r.tour;
    const n = pts.length;
    const isPerm =
      Array.isArray(t) && t.length === n &&
      t.every((c) => Number.isInteger(c) && c >= 0 && c < n) && new Set(t).size === n;
    ok(isPerm, `${tag}: stored tour is not a permutation of 0..${n - 1}`);
    if (!isPerm) return;
    let len = 0;
    for (let k = 0; k < n; k++) {
      const a = pts[t[k]], b = pts[t[(k + 1) % n]];
      len += Math.hypot(a[0] - b[0], a[1] - b[1]);
    }
    ok(near(len, r.length), `${tag}: recomputed length ${len} != stored ${r.length}`);
    ok(near(r.length / refs[i], r.ratio), `${tag}: ratio ${r.ratio} != length/2-opt ${r.length / refs[i]}`);
  });
  if (ev.valid) {
    ok(rows.length === instSet.instances.length, `${label}: wrong number of instances`);
    const mean = rows.reduce((s, r) => s + r.ratio, 0) / rows.length;
    ok(near(mean, ev.fitness), `${label}: mean ratio ${mean} != stored fitness ${ev.fitness}`);
  }
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

console.log("Loopforge data check\n  data: " + DATA);
if (!existsSync(join(DATA, "index.json"))) {
  console.log("  FAIL: index.json not found. Run `loopforge exp export ...` first.");
  process.exit(1);
}

const index = load("index.json");
const instances = load("instances.json");
const baselines = load("baselines.json");
for (const [name, doc] of [["index", index], ["instances", instances], ["baselines", baselines]]) {
  ok(doc.schema_version === 1, `${name}.json schema_version should be 1`);
}
const ids = index.experiments.map((e) => e.id).sort();
ok(JSON.stringify(ids) === JSON.stringify(["claude-01", "gpt-01"]), `experiments in index should be claude-01 and gpt-01, got ${ids}`);
if (!index.commit) warnings.push("index.json has no git commit hash (git not found when exporting?)");

const refDev = baselines.references.two_opt.dev.instances.map((r) => r.length);
const refTest = baselines.references.two_opt.test.instances.map((r) => r.length);
ok(near(baselines.references.two_opt.dev.fitness, 1), "two_opt dev fitness should be exactly 1");
ok(near(baselines.references.two_opt.test.fitness, 1), "two_opt test fitness should be exactly 1");
ok(near(baselines.references.nearest_neighbor.dev.fitness, SEED.dev), "nearest_neighbor dev fitness mismatch");
ok(near(baselines.references.nearest_neighbor.test.fitness, SEED.test), "nearest_neighbor test fitness mismatch");
ok(instances.dev.instances.length === 12 && instances.test.instances.length === 12, "expected 12 dev and 12 test instances");
checkEval("baseline two_opt dev", baselines.references.two_opt.dev, instances.dev, refDev);
checkEval("baseline two_opt test", baselines.references.two_opt.test, instances.test, refTest);
checkEval("baseline nearest_neighbor dev", baselines.references.nearest_neighbor.dev, instances.dev, refDev);
checkEval("baseline nearest_neighbor test", baselines.references.nearest_neighbor.test, instances.test, refTest);

const table = [];
for (const [id, exp] of Object.entries(EXPECTED)) {
  console.log("Checking " + id);
  if (!existsSync(join(DATA, "experiments", id + ".json"))) { ok(false, `${id}.json missing`); continue; }
  const doc = load(`experiments/${id}.json`);
  ok(doc.schema_version === 1, `${id}: schema_version`);
  ok(doc.turns.length === 7, `${id}: expected 7 records (seed + 6 turns), got ${doc.turns.length}`);
  ok(JSON.stringify(doc.turns.map((t) => t.status)) === JSON.stringify(exp.statuses), `${id}: turn statuses differ from the finalize output`);
  for (const k of Object.keys(exp.counts)) ok(doc.summary.counts[k] === exp.counts[k], `${id}: counts.${k} is ${doc.summary.counts[k]}, expected ${exp.counts[k]}`);
  ok(doc.summary.best.id === exp.best, `${id}: best id ${doc.summary.best.id}, expected ${exp.best}`);
  ok(near(doc.summary.best.dev_fitness, exp.dev, 1e-12), `${id}: best dev fitness`);
  ok(near(doc.summary.best.test_fitness, exp.test, 1e-12), `${id}: best test fitness`);
  ok(near(doc.summary.seed.dev_fitness, SEED.dev, 1e-12), `${id}: seed dev fitness`);
  ok(near(doc.summary.seed.test_fitness, SEED.test, 1e-12), `${id}: seed test fitness`);

  const known = new Set(doc.turns.map((t) => t.program_id));
  doc.turns.forEach((t, i) => {
    ok(t.turn === i, `${id}: turn numbering at index ${i}`);
    if (t.turn === 0) {
      ok(t.prompt == null && t.response == null, `${id}: seed should have no prompt or response`);
    } else {
      ok(typeof t.prompt === "string" && t.prompt.length > 0, `${id} turn ${t.turn}: prompt missing`);
      ok(typeof t.response === "string" && t.response.length > 0, `${id} turn ${t.turn}: response missing`);
      ok(known.has(t.parent_id), `${id} turn ${t.turn}: unknown parent ${t.parent_id}`);
    }
    if (t.status === "invalid") ok(!!t.error, `${id} turn ${t.turn}: invalid turn has no error text`);
    checkEval(`${id} turn ${t.turn}`, t.eval, instances.dev, refDev);
    // saved files must still hash to what the export recorded
    const dir = join(EVIDENCE, id, `turn-${String(t.turn).padStart(2, "0")}`);
    for (const [name, h] of Object.entries(t.hashes || {})) {
      const p = join(dir, name);
      if (!existsSync(p)) { ok(false, `${id} turn ${t.turn}: evidence file ${name} missing`); continue; }
      ok(sha(p) === h, `${id} turn ${t.turn}: ${name} no longer matches its recorded sha256`);
    }
  });

  checkEval(`${id} final best (test)`, doc.final.best.test, instances.test, refTest);
  checkEval(`${id} final seed (test)`, doc.final.seed.test, instances.test, refTest);
  ok(near(doc.final.best.test.fitness, exp.test, 1e-12), `${id}: final.json best test fitness`);

  table.push([id, doc.turns.map((t) => (t.fitness == null ? "invalid" : t.fitness.toFixed(4))).join("  "), doc.summary.best.test_fitness.toFixed(4)]);
}

console.log("Scanning exported files for personal paths or emails");
for (const root of [DATA, EVIDENCE]) {
  if (!existsSync(root)) continue;
  for (const p of walk(root)) {
    if (!/\.(json|md|py|jsonl)$/.test(p)) continue;
    const text = readFileSync(p, "utf8");
    const email = text.match(/[\w.+-]+@[\w-]+\.[a-z]{2,}/i);
    const winPath = text.match(/\b[A-Za-z]:\\\\[\w .-]+\\\\/);
    const unixPath = text.match(/\/(Users|home)\/[\w.-]+/);
    for (const [kind, m] of [["email", email], ["Windows path", winPath], ["home path", unixPath]]) {
      if (m) ok(false, `${p}: looks like it contains a ${kind}: ${m[0]}`);
    }
  }
}

console.log("\nDev fitness by turn (turn 0 = seed) and final held-out test fitness");
for (const [id, dev, test] of table) console.log(`  ${id.padEnd(10)} ${dev}   test ${test}`);
for (const w of warnings) console.log("  warning: " + w);
console.log(`\n${checks} checks, ${failures} failed. commit: ${index.commit || "unknown"}`);
process.exit(failures ? 1 : 0);
