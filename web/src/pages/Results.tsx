import "../styles/explorer.css";
import { useCore, useExperiment } from "../data/DataContext";
import { fitness } from "../lib/format";
import { Status } from "../components/Status";

const COLORS = { "gpt-01": "var(--model-gpt)", "claude-01": "var(--model-claude)" } as const;

export function Results() {
  const core = useCore();
  const g = useExperiment("gpt-01");
  const c = useExperiment("claude-01");
  const exps = [g, c].flatMap((e) => (e.status === "ready" ? [e.experiment] : []));
  const all = exps.flatMap((e) => e.curve);
  const lo = Math.min(...all), hi = Math.max(...all);
  const x = (i: number) => 24 + (i * 260) / 6;
  const y = (v: number) => 10 + ((hi - v) / (hi - lo || 1)) * 100;
  return (
    <>
      <h1>Results</h1>
      <p className="lede">Both models beat the nearest-neighbour seed and 2-opt on held-out test instances. One run each, so treat the gap between them as preliminary.</p>
      <Status core={core} />
      {core.status === "ready" && (
        <>
          <div className="table-wrap">
            <table>
              <caption>Fitness = mean(tour ÷ 2-opt tour). Lower is better.</caption>
              <thead><tr><th>Model</th><th className="num">Seed (test)</th><th className="num">Best (dev)</th><th className="num">Best (test)</th><th className="num">Gain vs 2-opt</th><th className="num">Improving turns</th><th className="num">Invalid</th></tr></thead>
              <tbody>
                {core.index.experiments.map((e) => (
                  <tr key={e.id}>
                    <td><span className="swatch" style={{ background: COLORS[e.id as keyof typeof COLORS] }} />{e.model}</td>
                    <td className="num">{fitness(e.seed_test)}</td>
                    <td className="num">{fitness(e.best_dev)}</td>
                    <td className="num">{fitness(e.best_test)}</td>
                    <td className="num">{((1 - e.best_test) * 100).toFixed(1)}%</td>
                    <td className="num">{e.improvements} of {e.proposals}</td>
                    <td className="num">{e.invalid}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2>Progress by turn</h2>
          <section className="card">
            <svg viewBox="0 0 300 130" className="curve" role="img" aria-label={exps.map((e) => `${e.meta.model}: ${e.curve.map((v) => v.toFixed(3)).join(", ")}`).join(". ")}>
              {exps.map((e) => (
                <polyline key={e.id} fill="none" strokeWidth="2" stroke={COLORS[e.id as keyof typeof COLORS]} points={e.curve.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
              ))}
              {[0, 1, 2, 3, 4, 5, 6].map((i) => <text key={i} x={x(i)} y="126" fontSize="8" textAnchor="middle" fill="var(--ink-soft)">{i}</text>)}
            </svg>
            <p className="soft small">Best dev fitness so far, by turn (0 = seed). Both curves flatten after turn 1–2.</p>
          </section>

          <h2>What stands out</h2>
          <ul>
            <li><strong>Most of the gain came immediately.</strong> The first AI reply took fitness from about 1.15 to under 0.98. Later turns added little or nothing.</li>
            <li><strong>Different strategies.</strong> GPT’s best program is a multi-start local search that finishes in under half a second. Claude’s runs a time-boxed perturbation search for several seconds per instance.</li>
            <li><strong>One failure.</strong> GPT’s turn 3 crashed with an <code>IndexError</code> and was rejected by the sandbox; the next turns were told about it.</li>
            <li><strong>Blind edits did not work.</strong> 9,000 random mutations of the seed: 0 improvements.</li>
          </ul>

          <h2>Reference points (test set)</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Method</th><th className="num">Fitness</th></tr></thead>
              <tbody>
                <tr><td>2-opt (reference)</td><td className="num">{fitness(core.baselines.references.two_opt.test.fitness)}</td></tr>
                <tr><td>Nearest neighbour (seed)</td><td className="num">{fitness(core.baselines.references.nearest_neighbor.test.fitness)}</td></tr>
                <tr><td>Random order</td><td className="num">{fitness(core.baselines.references.random_order.test.fitness)}</td></tr>
              </tbody>
            </table>
          </div>
          <p>Next: <a href="#/explorer/gpt-01/0">replay each turn in the explorer</a>, or read the <a href="#/methods">methods and limitations</a>.</p>
        </>
      )}
    </>
  );
}
