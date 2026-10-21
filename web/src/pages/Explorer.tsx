import { useEffect, useMemo, useRef, useState } from "react";
import "../styles/explorer.css";
import { useCore, useExperiment, type CoreState } from "../data/DataContext";
import { useRoute } from "../lib/useHashRoute";
import { fitness } from "../lib/format";
import { TourPlot } from "../components/TourPlot";
import { Status } from "../components/Status";
import type { Experiment } from "../data/types";

type Ready = Extract<CoreState, { status: "ready" }>;
const sec = (s: number | null) => (s == null ? "n/a" : s < 1 ? `${(s * 1000).toFixed(0)} ms` : `${s.toFixed(2)} s`);

export function Explorer() {
  const core = useCore();
  const route = useRoute();
  const id = route[1] ?? "gpt-01";
  const exp = useExperiment(id);
  return (
    <>
      <h1>Experiment explorer</h1>
      <p className="lede">Replay each turn, see the tour it produced, and open the raw evidence behind every number.</p>
      <Status core={core} />
      {core.status === "ready" && (
        <>
          <nav className="seg" aria-label="Experiment">
            {core.index.experiments.map((e) => (
              <a key={e.id} href={`#/explorer/${e.id}/0`} aria-current={e.id === id ? "true" : undefined}>
                <span className="swatch" style={{ background: e.site === "Claude" ? "var(--model-claude)" : "var(--model-gpt)" }} />
                {e.model}
              </a>
            ))}
          </nav>
          {exp.status === "loading" && <p role="status">Loading experiment…</p>}
          {exp.status === "error" && <div className="notice error" role="alert">{exp.message}</div>}
          {exp.status === "ready" && <Body key={id} exp={exp.experiment} core={core} />}
        </>
      )}
    </>
  );
}

function Body({ exp, core }: { exp: Experiment; core: Ready }) {
  const route = useRoute();
  const n = Math.min(Math.max(parseInt(route[2] ?? "0", 10) || 0, 0), exp.turns.length - 1);
  const t = exp.turns[n];
  const [inst, setInst] = useState(0);
  const [drawer, setDrawer] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const go = (k: number) => {
    if (k < 0 || k >= exp.turns.length) return;
    window.location.hash = `#/explorer/${exp.id}/${k}`;
    setInst(0);
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (drawer || e.altKey || e.ctrlKey || e.metaKey || tag === "SELECT" || tag === "INPUT") return;
      if (e.key === "ArrowLeft") go(n - 1);
      if (e.key === "ArrowRight") go(n + 1);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });

  const check = useMemo(() => {
    const ev = t.eval;
    if (!ev) return null;
    const rows = ev.instances.map((r, i) => {
      const pts = core.instances.dev.instances[i]?.points;
      const ref = core.baselines.references.two_opt.dev.instances[i]?.length ?? 1;
      if (!r.valid || !r.tour || !pts) return { valid: false, ok: true, ratio: 0 };
      let len = 0;
      for (let k = 0; k < r.tour.length; k++) {
        const a = pts[r.tour[k]], b = pts[r.tour[(k + 1) % r.tour.length]];
        len += Math.hypot(a[0] - b[0], a[1] - b[1]);
      }
      const perm = r.tour.length === pts.length && new Set(r.tour).size === pts.length;
      const ratio = len / ref;
      return { valid: true, ok: perm && Math.abs(len - (r.length ?? 0)) < 1e-9 && Math.abs(ratio - (r.ratio ?? 0)) < 1e-9, ratio };
    });
    const v = rows.filter((r) => r.valid);
    const mean = ev.valid && v.length ? v.reduce((s, r) => s + r.ratio, 0) / v.length : null;
    return { rows, allOk: v.every((r) => r.ok) && (mean == null || Math.abs(mean - (ev.fitness ?? 0)) < 1e-9), count: v.length };
  }, [t, core]);

  const row = t.eval?.instances[Math.min(inst, (t.eval?.instances.length ?? 1) - 1)];
  const pts = core.instances.dev.instances[Math.min(inst, 11)]?.points;
  const prev = n > 0 ? exp.turns[n - 1] : null;
  const color = exp.meta.site === "Claude" ? "var(--model-claude)" : "var(--model-gpt)";

  return (
    <div className="ex" style={{ ["--accent" as string]: color }}>
      <section aria-label="Fitness over turns" className="card">
        <Curve curve={exp.curve} at={n} />
        <p className="soft small">Dev fitness, best so far (lower is better). Turn 0 is the seed. Use ← → to step.</p>
      </section>

      <ol className="turns" aria-label="Turns">
        {exp.turns.map((x, i) => (
          <li key={i}>
            <a href={`#/explorer/${exp.id}/${i}`} aria-current={i === n ? "step" : undefined} className={`turn ${x.status}`}>
              <b>{i === 0 ? "Seed" : `Turn ${i}`}</b>
              <span className="num">{fitness(x.fitness)}</span>
              <small>{x.status === "invalid" ? "invalid" : x.improved ? "new best" : i === 0 ? "baseline" : "no gain"}</small>
            </a>
          </li>
        ))}
      </ol>

      <article className="card detail" aria-live="polite">
        <header className="bar">
          <h2>{n === 0 ? "Seed program" : `Turn ${n}`} <span className={`pill ${t.status}`}>{t.status}</span></h2>
          <div className="btns">
            <button onClick={() => go(n - 1)} disabled={n === 0}>← Prev</button>
            <button onClick={() => go(n + 1)} disabled={n === exp.turns.length - 1}>Next →</button>
          </div>
        </header>
        <dl className="facts">
          <div><dt>Fitness (dev)</dt><dd className="num">{fitness(t.fitness)}</dd></div>
          <div><dt>Change vs previous</dt><dd className="num">{t.fitness != null && prev?.fitness != null ? (t.fitness - prev.fitness).toFixed(4) : "n/a"}</dd></div>
          <div><dt>Mean time / instance</dt><dd className="num">{sec(t.mean_seconds)}</dd></div>
          <div><dt>Built on</dt><dd>{t.parent_id ?? "none"}</dd></div>
          {Object.entries(t.by_size).map(([k, v]) => (
            <div key={k}><dt>n = {k}</dt><dd className="num">{fitness(v)}</dd></div>
          ))}
        </dl>
        <p className="soft">Description: <em>not recorded</em> (the saved reply has no DESCRIPTION line).</p>
        {t.error && <div className="notice error" role="alert"><strong>Failed.</strong> <code>{t.error}</code></div>}

        {t.eval && t.eval.instances.length > 0 && (
          <div className="viz">
            <div className="plot">
              {row?.tour && pts ? (
                <TourPlot points={pts} tour={row.tour} label={`Tour for instance ${inst + 1}, ${row.n} cities, ratio ${fitness(row.ratio)}`} />
              ) : (
                <p className="soft">No tour: this instance did not produce a valid result.</p>
              )}
            </div>
            <div className="table-wrap">
              <table>
                <caption>Dev instances. Pick one to draw its tour.</caption>
                <thead><tr><th>#</th><th className="num">n</th><th className="num">Ratio</th><th className="num">Time</th><th>Recomputed</th></tr></thead>
                <tbody>
                  {t.eval.instances.map((r, i) => (
                    <tr key={i} className={i === inst ? "sel" : ""}>
                      <td><button className="link" aria-pressed={i === inst} onClick={() => setInst(i)}>{i + 1}</button></td>
                      <td className="num">{r.n}</td>
                      <td className="num">{fitness(r.ratio)}</td>
                      <td className="num">{sec(r.seconds)}</td>
                      <td>{r.valid ? (check?.rows[i]?.ok ? "✓ matches" : "✗ mismatch") : "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {check && (
          <p className={check.allOk ? "okmsg" : "badmsg"} role="status">
            {check.allOk ? "✓" : "✗"} Tour validity, length, ratio and mean fitness recomputed in your browser from the stored points
            ({check.count} valid instance{check.count === 1 ? "" : "s"}).
          </p>
        )}
        <button ref={opener} className="primary" onClick={() => setDrawer(true)}>Open evidence (prompt, reply, code)</button>
      </article>

      {drawer && <Drawer exp={exp} n={n} onClose={() => { setDrawer(false); opener.current?.focus(); }} />}
    </div>
  );
}

function Curve({ curve, at }: { curve: number[]; at: number }) {
  const lo = Math.min(...curve), hi = Math.max(...curve);
  const x = (i: number) => 20 + (i * 260) / (curve.length - 1);
  const y = (v: number) => 10 + ((hi - v) / (hi - lo || 1)) * 80;
  return (
    <svg viewBox="0 0 300 110" role="img" aria-label={`Fitness by turn: ${curve.map((v) => v.toFixed(3)).join(", ")}`} className="curve">
      <polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={curve.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
      {curve.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r={i === at ? 5 : 2.5} fill={i === at ? "var(--accent)" : "var(--surface)"} stroke="var(--accent)" strokeWidth="1.5" />
      ))}
      <text x="20" y="106" fontSize="8" fill="var(--ink-soft)">seed</text>
      <text x="280" y="106" fontSize="8" fill="var(--ink-soft)" textAnchor="end">turn {curve.length - 1}</text>
    </svg>
  );
}

type Tab = "prompt" | "response" | "code" | "eval";
const FILES: Record<Tab, string> = { prompt: "prompt.md", response: "response.md", code: "candidate.py", eval: "eval_dev.json" };

async function sha256(buf: ArrayBuffer) {
  const d = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function Drawer({ exp, n, onClose }: { exp: Experiment; n: number; onClose: () => void }) {
  const t = exp.turns[n];
  const [tab, setTab] = useState<Tab>("response");
  const [ver, setVer] = useState<string>("");
  const closeBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeBtn.current?.focus();
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);

  const text: Record<Tab, string | null> = {
    prompt: t.prompt,
    response: t.response,
    code: t.code,
    eval: t.eval ? JSON.stringify(t.eval, (k, v) => (k === "tour" ? undefined : v), 2) : null,
  };

  const verify = async () => {
    setVer("Checking…");
    try {
      const dir = `turn-${String(n).padStart(2, "0")}`;
      const out: string[] = [];
      for (const [name, h] of Object.entries(t.hashes)) {
        const res = await fetch(`${import.meta.env.BASE_URL}${exp.evidence}${dir}/${name}`);
        if (!res.ok) { out.push(`✗ ${name}: HTTP ${res.status}`); continue; }
        out.push(`${(await sha256(await res.arrayBuffer())) === h ? "✓" : "✗"} ${name}`);
      }
      setVer(out.join("   "));
    } catch {
      setVer("Could not verify (needs https or localhost for crypto).");
    }
  };

  return (
    <div className="scrim" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Evidence for turn ${n}`} onClick={(e) => e.stopPropagation()}>
        <header className="bar">
          <h2>Evidence · {n === 0 ? "seed" : `turn ${n}`}</h2>
          <button ref={closeBtn} onClick={onClose}>Close (Esc)</button>
        </header>
        <div role="tablist" aria-label="Evidence files" className="seg">
          {(Object.keys(FILES) as Tab[]).map((k) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{FILES[k]}</button>
          ))}
        </div>
        {tab === "response" && t.response && !/DESCRIPTION/i.test(t.response) && (
          <p className="soft small">This saved reply contains no DESCRIPTION line, so no description is shown for this turn.</p>
        )}
        <pre tabIndex={0} aria-label={FILES[tab]}>{text[tab] ?? "Not applicable: the seed program has no prompt or reply."}</pre>
        <footer>
          <button onClick={verify}>Verify files against recorded SHA-256</button>
          <p className="small" role="status">{ver}</p>
        </footer>
      </aside>
    </div>
  );
}
