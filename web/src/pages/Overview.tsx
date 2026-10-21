import { useCore } from "../data/DataContext";
import { fitness } from "../lib/format";
import { Status } from "../components/Status";

export function Overview() {
  const core = useCore();
  return (
    <>
      <h1>Can a language model improve a routing heuristic?</h1>
      <p className="lede">
        Loopforge asks GPT and Claude to rewrite Python code that solves the Traveling Salesman Problem, runs every
        answer in a sandbox, and scores it against a 2-opt reference. Every prompt, reply, program and score is kept.
      </p>
      <Status core={core} />
      {core.status === "ready" && (
        <>
          <h2>What was recorded</h2>
          <p>
            Two experiments, one per model. Each is a single chain of six turns, and every turn was a new chat with no
            memory of the others. With one run per model, a small gap between them is suggestive, not conclusive.
          </p>
          <div className="table-wrap">
            <table>
              <caption>Fitness is mean(tour length / 2-opt tour length). Lower is better; 1.0000 ties 2-opt.</caption>
              <thead>
                <tr>
                  <th>Model</th>
                  <th className="num">Valid</th>
                  <th className="num">Invalid</th>
                  <th className="num">Duplicate</th>
                  <th className="num">Seed (test)</th>
                  <th className="num">Best (dev)</th>
                  <th className="num">Best (test)</th>
                </tr>
              </thead>
              <tbody>
                {core.index.experiments.map((e) => (
                  <tr key={e.id}>
                    <td>
                      <span className="swatch" style={{ background: e.site === "Claude" ? "var(--model-claude)" : "var(--model-gpt)" }} />
                      {e.model} <span className="soft">({e.site})</span>
                    </td>
                    <td className="num">{e.valid}</td>
                    <td className="num">{e.invalid}</td>
                    <td className="num">{e.duplicate}</td>
                    <td className="num">{fitness(e.seed_test)}</td>
                    <td className="num">{fitness(e.best_dev)}</td>
                    <td className="num">{fitness(e.best_test)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            For comparison, 9,000 blind random edits to the same seed program produced 0 improvements. The dashboard,
            the turn-by-turn explorer and the methodology are coming in the next stages.
          </p>
        </>
      )}
    </>
  );
}
