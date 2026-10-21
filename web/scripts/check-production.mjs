// Run after `npm run build`:  node scripts/check-production.mjs
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
let fail = 0;
const ok = (c, m) => { if (!c) { fail++; console.log("  FAIL: " + m); } else console.log("  ok: " + m); };
const size = (d) => readdirSync(d).reduce((s, n) => { const p = join(d, n); return s + (statSync(p).isDirectory() ? size(p) : statSync(p).size); }, 0);
ok(existsSync(join(dist, "index.html")), "dist/index.html exists");
for (const f of ["data/index.json", "data/instances.json", "data/baselines.json", "data/experiments/gpt-01.json", "data/experiments/claude-01.json", "evidence/gpt-01/summary.json", "evidence/claude-01/summary.json"])
  ok(existsSync(join(dist, f)), `${f} shipped`);
if (existsSync(join(dist, "index.html"))) {
  const html = readFileSync(join(dist, "index.html"), "utf8");
  ok(!/(src|href)=["']https?:/i.test(html), "no external scripts or stylesheets (self-contained)");
  ok(/<title>.+<\/title>/.test(html) && /name="description"/.test(html), "title and meta description present");
  ok(/src="\.\//.test(html), "asset paths are relative (works on any static host)");
}
ok(!existsSync(join(dist, "evidence", "dry-run")) && !existsSync(join(dist, "data", "experiments", "dry-run.json")), "dry-run data excluded");
if (existsSync(dist)) console.log(`  dist size: ${(size(dist) / 1e6).toFixed(1)} MB`);
console.log(fail ? `\n${fail} check(s) failed` : "\nAll production checks passed");
process.exit(fail ? 1 : 0);
