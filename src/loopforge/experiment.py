"""Run several search strategies over several seeds, then summarize them honestly.

Every (strategy, seed) pair is one independent run with the same budget, the same
proposer and the same instance sets. The report shows dev-set fitness (what the
search optimized) next to held-out test-set fitness (what it did not see), so
overfitting is visible rather than hidden.
"""

from __future__ import annotations

import json
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from . import __version__
from .evaluator import evaluate
from .runlog import RunLogger
from .search import Search, SearchConfig
from .seeds import load_tsp_seed_source

REFERENCE_SEEDS = ("nearest_neighbor", "two_opt")


def _run_one(spec: dict) -> dict:
    """Execute a single run. Top-level so it can be sent to a worker process."""
    out_dir = Path(spec["out_dir"]) / spec["run_name"]
    config = SearchConfig.from_dict(spec["config"])
    result = Search(config, logger=RunLogger(out_dir)).run()
    return {"run_name": spec["run_name"], "summary": result.summary}


def reference_scores(config: SearchConfig) -> dict:
    """Dev and test fitness of the built-in baselines on the same instance sets."""
    dev, test = config.instance_sets()
    scores = {}
    for name in REFERENCE_SEEDS:
        source = load_tsp_seed_source(name)
        d = evaluate(source, dev, limits=config.limits)
        t = evaluate(source, test, limits=config.limits)
        scores[name] = {"dev": d.fitness if d.valid else None, "test": t.fitness if t.valid else None}
    return scores


def run_experiment(
    out_dir: Path,
    strategies: list[str],
    seeds: list[int],
    base_config: SearchConfig,
    workers: int = 1,
    progress: Callable[[str], None] | None = None,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda _msg: None)

    specs = []
    for strategy in strategies:
        for seed in seeds:
            cfg = SearchConfig.from_dict({**base_config.to_dict(), "strategy": strategy, "seed": seed})
            specs.append({"out_dir": str(out_dir), "run_name": f"{strategy}-s{seed}", "config": cfg.to_dict()})

    experiment = {
        "version": __version__,
        "strategies": strategies,
        "seeds": seeds,
        "base_config": base_config.to_dict(),
        "references": reference_scores(base_config),
        "runs": [s["run_name"] for s in specs],
    }
    (out_dir / "experiment.json").write_text(json.dumps(experiment, indent=2) + "\n")

    def finished(item: dict) -> None:
        s = item["summary"]
        say(
            f"  done {item['run_name']:<16} dev {s['best']['dev_fitness']:.4f}  "
            f"test {s['best']['test_fitness']:.4f}  ({s['wall_seconds']:.0f}s)"
        )

    if workers <= 1:
        for spec in specs:
            finished(_run_one(spec))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(_run_one, s) for s in specs]):
                finished(future.result())
    return experiment


# ---------------------------------------------------------------- reporting


def _mean_sd(values: list[float]) -> tuple[float, float | None]:
    mean = statistics.fmean(values)
    return mean, (statistics.stdev(values) if len(values) >= 2 else None)


def _fmt(values: list[float], digits: int = 4) -> str:
    if not values:
        return "n/a"
    mean, sd = _mean_sd(values)
    return f"{mean:.{digits}f}" + (f" ± {sd:.{digits}f}" if sd is not None else "")


def aggregate(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    experiment = json.loads((out_dir / "experiment.json").read_text())
    per_strategy: dict[str, list[dict]] = {s: [] for s in experiment["strategies"]}
    for run_name in experiment["runs"]:
        path = out_dir / run_name / "summary.json"
        if path.exists():
            summary = json.loads(path.read_text())
            per_strategy[summary["config"]["strategy"]].append(summary)
    return {"experiment": experiment, "per_strategy": per_strategy}


def format_report(agg: dict) -> str:
    exp = agg["experiment"]
    cfg = exp["base_config"]
    refs = exp["references"]
    lines = [
        f"# Experiment report: {cfg['proposer']} proposer, seed program `{cfg['seed_program']}`",
        "",
        f"Budget {cfg['budget']} proposals per run. Instance sizes {cfg['sizes']} x {cfg['per_size']} each. "
        "Fitness is mean(tour length / 2-opt tour length): lower is better, 1.0 ties 2-opt.",
        "Dev = what the search optimized. Test = held-out instances the search never saw.",
        "",
        "| Strategy | Runs | Best dev | Best test | Test − dev | Valid / invalid / dup % | Improvements |",
        "|---|---|---|---|---|---|---|",
    ]
    for strategy, runs in agg["per_strategy"].items():
        if not runs:
            continue
        dev = [r["best"]["dev_fitness"] for r in runs]
        tst = [r["best"]["test_fitness"] for r in runs if r["best"]["test_fitness"] is not None]
        gap = [r["best"]["test_fitness"] - r["best"]["dev_fitness"] for r in runs if r["best"]["test_fitness"] is not None]
        total = sum(r["counts"]["proposals"] for r in runs)
        pct = lambda key: 100 * sum(r["counts"][key] for r in runs) / total  # noqa: E731
        imps = statistics.fmean(r["counts"]["improvements"] for r in runs)
        lines.append(
            f"| {strategy} | {len(runs)} | {_fmt(dev)} | {_fmt(tst)} | {_fmt(gap)} | "
            f"{pct('valid'):.0f} / {pct('invalid'):.0f} / {pct('duplicate'):.0f} | {imps:.1f} |"
        )
    lines += ["", "Mean best-so-far dev fitness at checkpoints:", "", "| Strategy | 25% | 50% | 100% |", "|---|---|---|---|"]
    for strategy, runs in agg["per_strategy"].items():
        if not runs:
            continue
        cells = []
        for frac in (0.25, 0.5, 1.0):
            vals = [r["curve"][round(frac * (len(r["curve"]) - 1))] for r in runs]
            cells.append(f"{statistics.fmean(vals):.4f}")
        lines.append(f"| {strategy} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Reference algorithms on the same instances:",
        "",
        "| Algorithm | Dev | Test |",
        "|---|---|---|",
    ]
    for name, score in refs.items():
        lines.append(f"| {name} | {score['dev']:.4f} | {score['test']:.4f} |")
    lines += [
        "",
        "Values are mean ± sample standard deviation over runs. With few runs, treat small "
        "differences as noise.",
    ]
    return "\n".join(lines) + "\n"
