"""Command-line entry point: baselines, eval, doctor, search, experiment, report."""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import sys
from pathlib import Path

from .archive import Archive, Program
from .evaluator import evaluate
from .experiment import aggregate, format_report, run_experiment
from . import manual
from .llmclient import PRESETS, LLMError, resolve_model
from .proposers.llm import HINTS, build_prompt
from .runlog import RunLogger, load_run, unique_run_dir
from .sandbox import probe_sandbox
from .search import Search, SearchConfig
from .seeds import load_tsp_seed_source, tsp_seed_names
from .sourcetools import normalize_source, precheck
from .tasks.tsp import dev_set, test_set
from .usage import experiment_usage, format_usage, summarize_usage


def _get_set(name: str):
    return dev_set() if name == "dev" else test_set()


def cmd_baselines(args: argparse.Namespace) -> int:
    instance_set = _get_set(args.set)
    print(f"Instance set: {instance_set.name} ({len(instance_set)} instances)")
    print("Fitness = mean(tour length / 2-opt tour length). Lower is better; 1.000 = ties 2-opt.\n")
    print(f"{'candidate':<18}{'valid':<8}{'fitness':<10}{'mean sec':<10}")
    print("-" * 46)
    for name in tsp_seed_names():
        result = evaluate(load_tsp_seed_source(name), instance_set)
        fit = f"{result.fitness:.3f}" if result.valid else "-"
        print(f"{name:<18}{str(result.valid):<8}{fit:<10}{result.mean_seconds:<10.4f}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Report which sandbox protections this machine actually enforces."""
    outcome = probe_sandbox()
    print(f"platform: {platform.system()} {platform.release()}, python {platform.python_version()}")
    if outcome.fatal:
        print(f"SANDBOX BROKEN: {outcome.fatal}")
        return 1
    labels = {
        "cpu": "CPU time limit",
        "memory": "memory limit",
        "files": "no file writes",
        "core": "no core dumps",
    }
    for key, label in labels.items():
        print(f"  [{'x' if key in outcome.limits_applied else ' '}] {label}")
    print(f"  [{'x' if outcome.alarm_available else ' '}] per-instance timeout alarm")
    print("  [x] wall-clock timeout, process isolation, restricted builtins/imports")
    missing = [k for k in labels if k not in outcome.limits_applied]
    if missing or not outcome.alarm_available:
        print("\nSome OS-level protections are unavailable here (normal on Windows/macOS).")
        print("The wall-clock timeout still stops runaway code. See docs/SANDBOX.md.")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    source = Path(args.file).read_text(encoding="utf-8")
    result = evaluate(source, _get_set(args.set), sandboxed=not args.no_sandbox)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    elif result.valid:
        print(f"valid, fitness {result.fitness:.4f}, mean {result.mean_seconds:.4f}s per instance")
    else:
        print(f"INVALID: {result.error}")
    return 0 if result.valid else 1


def _sizes(text: str) -> tuple[int, ...]:
    return tuple(int(s) for s in text.split(",") if s.strip())


def _llm_options(args: argparse.Namespace) -> dict:
    """LLM settings for config.json. Contains no secrets (keys come from the environment)."""
    provider = args.provider or os.environ.get("LOOPFORGE_PROVIDER") or "gemini"
    options = {
        "provider": provider,
        "model": resolve_model(provider, args.model),
        "temperature": args.temperature,
        "max_cost_usd": args.max_cost,
        "max_total_tokens": args.max_tokens,
        "price_in": args.price_in,
        "price_out": args.price_out,
        "min_interval": args.min_interval,
        "use_hints": not args.no_hints,
        "cache": not args.no_cache,
    }
    return {k: v for k, v in options.items() if v is not None}


def _config_from_args(args: argparse.Namespace, **overrides) -> SearchConfig:
    values = dict(
        proposer=args.proposer, budget=args.budget, seed_program=args.seed_program,
        sizes=_sizes(args.sizes), per_size=args.per_size,
        proposer_options=_llm_options(args) if args.proposer == "llm" else {},
    )
    values.update(overrides)
    return SearchConfig(**values)


def cmd_search(args: argparse.Namespace) -> int:
    config = _config_from_args(args, strategy=args.strategy, seed=args.seed)
    name = args.name or f"{config.proposer}-{config.strategy}-s{config.seed}"
    run_dir = unique_run_dir(Path(args.out), name)

    def progress(i, budget, program, best):
        marker = ""
        if program.is_valid and best is not None and program.id == best.id:
            marker = f"  NEW BEST {program.fitness:.4f}  {program.description}"
        if marker or i % 25 == 0 or i == budget:
            print(f"[{i:>4}/{budget}] best {best.fitness:.4f}{marker}")

    print(f"Run directory: {run_dir}")
    try:
        result = Search(config, logger=RunLogger(run_dir), progress=progress).run()
    except LLMError as exc:
        print(f"\nStopped: {exc}\nPartial log kept in {run_dir}", file=sys.stderr)
        return 2
    s = result.summary
    print(
        f"\nSeed {s['seed']['dev_fitness']:.4f} -> best {s['best']['dev_fitness']:.4f} on dev; "
        f"held-out test: {s['seed']['test_fitness']:.4f} -> {s['best']['test_fitness']:.4f}"
    )
    c = s["counts"]
    print(f"{c['valid']} valid, {c['invalid']} invalid, {c['duplicate']} duplicate; {c['improvements']} improvements")
    if s.get("stopped_early"):
        print(f"Stopped early after {c['valid'] + c['invalid'] + c['duplicate']} proposals: {s['stopped_early']}")
    usage = format_usage(s.get("usage", {}), c["improvements"])
    if usage:
        print(usage)
    print(f"Best program saved to {run_dir / 'best.py'}")
    return 0


def cmd_experiment(args: argparse.Namespace) -> int:
    base = _config_from_args(args)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    out_dir = Path(args.out)
    print(f"Running {len(strategies)} strategies x {args.seeds} seeds, budget {base.budget}, into {out_dir}")
    try:
        run_experiment(out_dir, strategies, list(range(args.seeds)), base, workers=args.workers, progress=print)
    except LLMError as exc:
        print(f"\nStopped: {exc}\nFinished runs are kept in {out_dir}; re-running is cheap (replies are cached).", file=sys.stderr)
        return 2
    report = format_report(aggregate(out_dir))
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    usage = format_usage(experiment_usage(out_dir))
    if usage:
        print(usage)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    if (directory / "experiment.json").exists():
        print(format_report(aggregate(directory)))
        usage = format_usage(experiment_usage(directory))
        if usage:
            print("\n" + usage)
        return 0
    run = load_run(directory)
    print(f"Run {run.directory.name}: strategy {run.config['strategy']}, proposer {run.config['proposer']}")
    best = None
    for p in run.programs:
        if p.is_valid and (best is None or p.fitness < best - 1e-12):
            note = "seed" if p.iteration == 0 else p.description
            print(f"  iter {p.iteration:>4}  {p.fitness:.4f}  {note}")
            best = p.fitness
    if run.summary:
        s = run.summary
        print(f"\nHeld-out test fitness: seed {s['seed']['test_fitness']:.4f} -> best {s['best']['test_fitness']:.4f}")
    else:
        print("\n(run did not finish; no summary.json)")
    usage = format_usage(summarize_usage(run.programs))
    if usage:
        print("\n" + usage)
    return 0


def cmd_llm_check(args: argparse.Namespace) -> int:
    """Show the prompt, or make ONE real call and score the reply: a cheap end-to-end test."""
    seed_source = normalize_source(load_tsp_seed_source("nearest_neighbor"))
    seed_result = evaluate(seed_source, dev_set())
    seed = Program("p0000", None, 0, seed_source, "valid", seed_result.fitness,
                   Search._by_size(seed_result), seed_result.mean_seconds)
    archive = Archive()
    archive.add(seed)
    rng = random.Random(0)
    if args.show_prompt:
        system, user = build_prompt(seed, archive, hint=None if args.no_hints else rng.choice(HINTS))
        print(f"--- system ---\n{system}\n\n--- user ---\n{user}")
        return 0
    from .proposers import get_proposer

    try:
        proposer = get_proposer("llm", _llm_options(args))
        print(f"Calling {proposer.provider} / {proposer.model} once ...")
        proposal = proposer.propose(seed, archive, rng)
    except LLMError as exc:
        print(f"LLM check failed: {exc}", file=sys.stderr)
        return 2
    info = proposal.info
    print(f"Reply parsed. Description: {proposal.description}")
    print(f"Tokens: {info['input_tokens']} in, {info['output_tokens']} out"
          f"{' (replayed from cache)' if info['cached'] else ''}")
    problem = precheck(proposal.source)
    if problem:
        print(f"Program rejected before running: {problem}")
        return 1
    result = evaluate(proposal.source, dev_set())
    if result.valid:
        print(f"Program is valid. Fitness {result.fitness:.4f} (seed nearest_neighbor: {seed.fitness:.4f})")
        return 0
    print(f"Program is invalid: {result.error}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loopforge", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("baselines", help="score the built-in baseline algorithms")
    p.add_argument("--set", choices=["dev", "test"], default="dev")
    p.set_defaults(func=cmd_baselines)

    p = sub.add_parser("eval", help="score a candidate file that defines solve(points)")
    p.add_argument("file")
    p.add_argument("--set", choices=["dev", "test"], default="dev")
    p.add_argument("--json", action="store_true", help="print full per-instance results")
    p.add_argument(
        "--no-sandbox",
        action="store_true",
        help="run in this process (ONLY for code you wrote and trust)",
    )
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("doctor", help="check which sandbox protections work on this machine")
    p.set_defaults(func=cmd_doctor)

    def add_llm_options(p):
        g = p.add_argument_group("LLM options (only used with --proposer llm / llm-check)")
        g.add_argument("--provider", choices=sorted(PRESETS), help="default: $LOOPFORGE_PROVIDER or gemini")
        g.add_argument("--model", help="default: $LOOPFORGE_MODEL or the provider's default")
        g.add_argument("--temperature", type=float, default=0.7)
        g.add_argument("--max-cost", type=float, help="stop a run after this many USD (needs --price-in/--price-out)")
        g.add_argument("--max-tokens", type=int, help="stop a run after this many billed tokens")
        g.add_argument("--price-in", type=float, help="USD per million input tokens (omit for free tiers)")
        g.add_argument("--price-out", type=float, help="USD per million output tokens")
        g.add_argument("--min-interval", type=float, help="seconds between calls (default: per provider)")
        g.add_argument("--no-hints", action="store_true", help="do not add TSP-specific suggestions to the prompt")
        g.add_argument("--no-cache", action="store_true", help="always call the API; do not replay stored replies")

    def add_search_options(p):
        add_llm_options(p)
        p.add_argument("--proposer", default="mutation")
        p.add_argument("--budget", type=int, default=200, help="number of proposals per run")
        p.add_argument("--seed-program", default="nearest_neighbor", choices=tsp_seed_names())
        p.add_argument("--sizes", default="25,50,100", help="instance sizes, comma separated")
        p.add_argument("--per-size", type=int, default=4, help="instances per size")
        p.add_argument("--out", default="runs", help="directory for run logs")

    p = sub.add_parser("llm-check", help="test your LLM setup with one call (or --show-prompt, no key needed)")
    add_llm_options(p)
    p.add_argument("--show-prompt", action="store_true", help="print the prompt and exit; makes no API call")
    p.set_defaults(func=cmd_llm_check)

    p = sub.add_parser("search", help="run one search and log it")
    add_search_options(p)
    p.add_argument("--strategy", choices=["random", "hill_climb", "evolve"], default="evolve")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--name", help="run directory name (default: proposer-strategy-seed)")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("experiment", help="compare strategies over several seeds")
    add_search_options(p)
    p.add_argument("--strategies", default="random,hill_climb,evolve")
    p.add_argument("--seeds", type=int, default=5, help="number of seeds (0..N-1)")
    p.add_argument("--workers", type=int, default=1, help="parallel runs (timing limits assume an idle machine)")
    p.set_defaults(func=cmd_experiment)

    p = sub.add_parser("report", help="summarize a run directory or an experiment directory")
    p.add_argument("directory")
    p.set_defaults(func=cmd_report)

    manual.register(sub)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
