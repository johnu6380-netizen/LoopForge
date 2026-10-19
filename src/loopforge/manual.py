"""Manual experiments: a human carries prompts to an AI website and replies back.

Instead of calling an API, you run ``loopforge exp ...`` commands that

  new       create an experiment folder and score its seed program
  prompt    write the next prompt (chosen by the hill-climb rule) for you to paste into a chat
  ingest    read the reply you pasted back, check it, run it in the sandbox, and record the result
  status    show what has happened so far
  finalize  score the best program on the held-out test set (once, ever)
  export    write static JSON for the web replay

Everything reuses the normal machinery: ``build_prompt`` and ``parse_response`` from the LLM
proposer, the sandbox and evaluator, the archive, and the same honesty guards as ``search.py``
(duplicate detection, a determinism re-check on every new best, dev-only feedback, one-shot test set).
Each experiment folder also doubles as an ordinary run folder, so ``loopforge report <folder>`` works.

Folder layout (see docs/EXPERIMENTS.md)::

    experiments/<id>/
        meta.json  config.json  programs.jsonl  summary.json  best.py  final.json
        turn-00/  candidate.py  eval_dev.json                         (the seed)
        turn-01/  prompt.md  prompt.json  response.md  candidate.py  eval_dev.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

from . import __version__
from .archive import DUPLICATE, INVALID, VALID, Archive, Program
from .evaluator import EvalResult, evaluate
from .experiment import aggregate
from .proposers.llm import HINTS, build_prompt, parse_response
from .safety import lint_source
from .sandbox import SandboxLimits
from .search import EPS, VERIFY_TOLERANCE, HillClimbStrategy, Search, SearchConfig
from .seeds import load_tsp_seed_source, tsp_seed_names
from .sourcetools import normalize_source, precheck, source_key
from .tasks.tsp import DEFAULT_PER_SIZE, DEFAULT_SIZES
from .usage import summarize_usage

SCHEMA_VERSION = 1
DEFAULT_DIR = "experiments"
DEFAULT_SETTINGS = "code execution off, memory off, new chat for every round"
REFERENCES = ("nearest_neighbor", "two_opt", "random_order")

# A better algorithm legitimately does more work than the 1-second limit used for the offline
# blind-mutation runs, so manual experiments default to 10 seconds per instance. The prompt tells
# the AI the real number. (A reference 2-opt solves an instance in about 5 ms.)
DEFAULT_TIME_LIMIT = 10.0
_TIME_SENTENCE = "takes more than about one\nsecond on an instance"


def _seconds(value: float) -> str:
    return f"{value:g} second" + ("" if value == 1 else "s")

# The prompt starts with this line, so the instruction is part of the recorded evidence.
PREAMBLE = (
    "Answer directly in the format requested at the end. Do not use any tools, do not run or "
    "test code, and do not browse the web.\n\n"
)

# Results of the offline blind-mutation experiments already documented in docs/RESULTS.md.
BLIND_FROM_RESULTS_MD = {
    "nearest_neighbor": {
        "runs": 30, "proposals": 9000, "improvements": 0,
        "source": "docs/RESULTS.md, Experiment 1 (3 strategies x 10 seeds x 300 proposals)",
    },
    "random_order": {
        "runs": 15, "proposals": 4500, "improvements": 0,
        "source": "docs/RESULTS.md, Experiment 2 (3 strategies x 5 seeds x 300 proposals)",
    },
}


class ExperimentError(Exception):
    """Something the user can fix (wrong id, missing file, ...). Shown without a traceback."""


# ---------------------------------------------------------------- small helpers


def _dumps(obj: object, **kwargs) -> str:
    return json.dumps(obj, allow_nan=False, **kwargs)


def _read(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ExperimentError(f"{path} is not UTF-8 text. Re-save it as UTF-8 (VS Code: bottom-right encoding).") from None


def _write(path: Path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _eval_record(program_id: str, status: str, result: EvalResult | None, note: str | None = None) -> dict:
    return {"program_id": program_id, "status": status, "note": note,
            "eval": result.to_dict() if result is not None else None}


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------- the experiment folder


class Experiment:
    def __init__(self, root: Path) -> None:
        self.dir = Path(root)
        meta_path = self.dir / "meta.json"
        if not meta_path.exists():
            raise ExperimentError(f"no experiment at {self.dir}. Create one with: loopforge exp new <id> ...")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        raw.pop("run_id", None)
        raw.pop("version", None)
        self.config = SearchConfig.from_dict(raw)

    @classmethod
    def open(cls, base: str | Path, exp_id: str) -> "Experiment":
        return cls(Path(base) / exp_id)

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def max_turns(self) -> int:
        return self.config.budget

    def turn_dir(self, turn: int) -> Path:
        return self.dir / f"turn-{turn:02d}"

    @property
    def finalized(self) -> bool:
        return (self.dir / "final.json").exists()

    def archive(self) -> Archive:
        archive = Archive()
        for line in (self.dir / "programs.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                program = Program.from_dict(json.loads(line))
                archive.add(program, source_key(program.source) if program.source else None)
        return archive

    def append_program(self, program: Program) -> None:
        with (self.dir / "programs.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(_dumps(program.to_dict()) + "\n")
            f.flush()


def create_experiment(
    base: str | Path, exp_id: str, *, seed_program: str, model: str, site: str, title: str = "",
    hints: bool = False, max_turns: int = 6, settings: str = DEFAULT_SETTINGS, notes: str = "",
    sizes: tuple[int, ...] = DEFAULT_SIZES, per_size: int = DEFAULT_PER_SIZE,
    time_limit: float = DEFAULT_TIME_LIMIT,
) -> Experiment:
    root = Path(base) / exp_id
    if root.exists():
        raise ExperimentError(f"{root} already exists. Pick another id (experiments are never overwritten).")
    if seed_program not in tsp_seed_names():
        raise ExperimentError(f"unknown seed program {seed_program!r}; choose from {tsp_seed_names()}")
    if not exp_id.replace("-", "").replace("_", "").isalnum():
        raise ExperimentError("the id may only contain letters, digits, '-' and '_'")
    if not 0 < time_limit <= 60:
        raise ExperimentError("--time-limit must be between 0 and 60 seconds per instance")

    config = SearchConfig(
        strategy="hill_climb", proposer="manual", budget=max_turns, seed_program=seed_program,
        sizes=tuple(sizes), per_size=per_size, limits=SandboxLimits(per_instance_seconds=float(time_limit)),
        proposer_options={"site": site, "model": model, "hints": hints, "settings": settings},
    )
    dev, _ = config.instance_sets()
    seed_source = normalize_source(load_tsp_seed_source(seed_program))
    assert seed_source is not None
    result = evaluate(seed_source, dev, limits=config.limits, keep_tours=True)
    if not result.valid:
        raise ExperimentError(f"the seed program {seed_program!r} is invalid: {result.error}")
    seed = Program(
        id="p0000", parent_id=None, iteration=0, source=seed_source, status=VALID,
        fitness=result.fitness, by_size=Search._by_size(result), mean_seconds=result.mean_seconds,
        description=f"seed: {seed_program}", proposer="seed",
    )

    root.mkdir(parents=True)
    meta = {
        "schema_version": SCHEMA_VERSION, "id": exp_id, "title": title or exp_id, "site": site,
        "model": model, "settings": settings, "seed_program": seed_program, "hints": hints,
        "max_turns": max_turns, "time_limit_seconds": float(time_limit), "notes": notes,
        "loopforge_version": __version__,
    }
    _write(root / "meta.json", _dumps(meta, indent=2) + "\n")
    _write(root / "config.json", _dumps({"run_id": exp_id, "version": __version__, **config.to_dict()}, indent=2) + "\n")
    _write(root / "programs.jsonl", _dumps(seed.to_dict()) + "\n")
    _write(root / "turn-00" / "candidate.py", seed_source.rstrip() + "\n")
    _write(root / "turn-00" / "eval_dev.json", _dumps(_eval_record("p0000", VALID, result), indent=1) + "\n")
    return Experiment(root)


# ---------------------------------------------------------------- prompt


def make_prompt(exp: Experiment) -> tuple[int, Path, bool]:
    """Write (or find) the prompt for the next turn. Returns (turn, path, newly_written)."""
    if exp.finalized:
        raise ExperimentError("this experiment is finalized; no more turns can be added")
    archive = exp.archive()
    turn = len(archive)  # the seed is program 0, so the next proposal is turn len(archive)
    if turn > exp.max_turns:
        raise ExperimentError(f"all {exp.max_turns} turns are used. Next step: loopforge exp finalize {exp.id}")
    tdir = exp.turn_dir(turn)
    path = tdir / "prompt.md"
    if path.exists():
        return turn, path, False  # never regenerate: the saved text is what was pasted

    strategy = HillClimbStrategy()
    for program in archive:
        strategy.observe(program)
    parent = strategy.select(archive, random.Random(0))
    hint = random.Random(f"{exp.id}:{turn}").choice(HINTS) if exp.meta["hints"] else None
    system, user = build_prompt(parent, archive, hint=hint)
    if _TIME_SENTENCE not in user:  # the shared prompt text changed; fail loudly rather than misreport the limit
        raise ExperimentError("internal error: could not find the time-limit sentence in the prompt template")
    user = user.replace(_TIME_SENTENCE, f"takes more than {_seconds(exp.config.limits.per_instance_seconds)} on an instance")
    text = PREAMBLE + system + "\n\n" + user
    _write(path, text.rstrip() + "\n")
    _write(tdir / "prompt.json", _dumps({"turn": turn, "parent_id": parent.id, "hint": hint,
                                         "sha256": _sha_text(text.rstrip() + "\n")}, indent=2) + "\n")
    return turn, path, True


# ---------------------------------------------------------------- ingest


def ingest_turn(exp: Experiment) -> tuple[Program, bool]:
    """Record the reply saved in the pending turn. Returns (program, improved_the_best)."""
    if exp.finalized:
        raise ExperimentError("this experiment is finalized; no more turns can be added")
    archive = exp.archive()
    turn = len(archive)
    if turn > exp.max_turns:
        raise ExperimentError(f"all {exp.max_turns} turns are used. Next step: loopforge exp finalize {exp.id}")
    tdir = exp.turn_dir(turn)
    if not (tdir / "prompt.md").exists():
        raise ExperimentError(f"no prompt for turn {turn} yet. Run: loopforge exp prompt {exp.id}")
    response_path = tdir / "response.md"
    if not response_path.exists():
        raise ExperimentError(f"paste the AI's full reply into {response_path} and save it, then run ingest again.")
    response = _read(response_path)
    if not response.strip():
        raise ExperimentError(f"{response_path} is empty. Paste the AI's full reply into it.")

    pmeta = json.loads((tdir / "prompt.json").read_text(encoding="utf-8"))
    parent = archive.get(pmeta["parent_id"])
    best_before = archive.best().fitness  # type: ignore[union-attr]
    pid = archive.next_id()
    cfg = exp.config

    info = {"site": exp.meta["site"], "model": exp.meta["model"], "hint": pmeta["hint"], "turn": turn}
    source, description = "", ""
    status, error, result, duplicate_of, note = INVALID, None, None, None, None
    fitness, by_size, mean_seconds = None, {}, None

    try:
        source, description = parse_response(response)
    except ValueError as exc:
        error = f"unusable reply: {exc}"
    else:
        earlier = archive.lookup(source_key(source))
        problems = lint_source(source)
        problem = precheck(source)
        if earlier is not None:
            status, duplicate_of = DUPLICATE, earlier.id
            fitness, by_size, error = earlier.fitness, dict(earlier.by_size), earlier.error
            note = f"identical to {earlier.id} after normalizing; not re-evaluated"
        elif problems:
            error = "rejected by the safety pre-check (not run): " + "; ".join(problems)
        elif problem is not None:
            error = problem
        else:
            dev, _ = cfg.instance_sets()
            result = evaluate(source, dev, limits=cfg.limits, keep_tours=True)
            if result.valid and result.fitness < best_before - EPS:
                again = evaluate(source, dev, limits=cfg.limits)
                if not again.valid or abs(again.fitness - result.fitness) > VERIFY_TOLERANCE:
                    second = f"{again.fitness:.6f}" if again.valid else "invalid"
                    result = EvalResult(
                        valid=False, fitness=math.inf, mean_seconds=result.mean_seconds,
                        instances=result.instances,
                        error=f"non-deterministic: scored {result.fitness:.6f}, then {second}",
                    )
            if result.valid:
                status, fitness = VALID, result.fitness
                by_size, mean_seconds = Search._by_size(result), result.mean_seconds
            else:
                error, mean_seconds = result.error, result.mean_seconds

    program = Program(
        id=pid, parent_id=parent.id, iteration=turn, source=source, status=status, fitness=fitness,
        by_size=by_size, mean_seconds=mean_seconds, error=error, description=description,
        proposer="manual", duplicate_of=duplicate_of, info=info,
    )
    if source:
        _write(tdir / "candidate.py", source)
    _write(tdir / "eval_dev.json", _dumps(_eval_record(pid, status, result, note), indent=1) + "\n")
    exp.append_program(program)
    improved = program.is_valid and program.fitness < best_before - EPS  # type: ignore[operator]
    return program, improved


# ---------------------------------------------------------------- finalize


def finalize_experiment(exp: Experiment) -> dict:
    """Score the best program and the seed on the held-out test set. Only ever runs once."""
    if exp.finalized:
        raise ExperimentError("already finalized. The test set may only be used once per experiment.")
    archive = exp.archive()
    if len(archive) < 2:
        raise ExperimentError("no turns have been ingested yet; nothing to finalize.")
    if (exp.turn_dir(len(archive)) / "prompt.md").exists() and len(archive) <= exp.max_turns:
        raise ExperimentError(
            f"turn {len(archive)} has a prompt but no ingested reply. Ingest it, or delete that folder "
            "if you are abandoning it, then run finalize again."
        )
    cfg = exp.config
    _, test = cfg.instance_sets()
    seed, best = archive.get("p0000"), archive.best()
    assert best is not None
    best_result = evaluate(best.source, test, limits=cfg.limits, keep_tours=True)
    seed_result = best_result if best is seed else evaluate(seed.source, test, limits=cfg.limits, keep_tours=True)

    curve, running, improvements = [seed.fitness], seed.fitness, 0
    for p in list(archive)[1:]:
        if p.is_valid and p.fitness < running - EPS:  # type: ignore[operator]
            running, improvements = p.fitness, improvements + 1
        curve.append(running)
    counts = archive.counts()
    test_f = lambda r: r.fitness if r.valid else None  # noqa: E731
    summary = {
        "run_id": exp.id, "version": __version__, "config": cfg.to_dict(),
        "seed": {"id": seed.id, "dev_fitness": seed.fitness, "test_fitness": test_f(seed_result)},
        "best": {
            "id": best.id, "iteration": best.iteration, "dev_fitness": best.fitness,
            "test_fitness": test_f(best_result), "lineage": [p.id for p in archive.lineage(best.id)],
            "description": best.description,
        },
        "counts": {"proposals": len(archive) - 1, "valid": counts[VALID] - 1, "invalid": counts[INVALID],
                   "duplicate": counts[DUPLICATE], "improvements": improvements},
        "curve": curve, "stopped_early": None, "usage": summarize_usage(archive), "wall_seconds": 0.0,
    }
    final = {
        "best": {"program_id": best.id, "iteration": best.iteration, "dev_fitness": best.fitness,
                 "test": best_result.to_dict()},
        "seed": {"program_id": seed.id, "dev_fitness": seed.fitness, "test": seed_result.to_dict()},
    }
    _write(exp.dir / "best.py", best.source.rstrip() + "\n")
    _write(exp.dir / "summary.json", _dumps(summary, indent=2) + "\n")
    _write(exp.dir / "final.json", _dumps(final) + "\n")  # written last: its existence is the one-shot guard
    return summary


# ---------------------------------------------------------------- export for the web replay


def summarize_blind(directory: str | Path) -> tuple[str, dict]:
    """Summarize an offline `loopforge experiment` folder as a blind-mutation baseline."""
    agg = aggregate(Path(directory))
    runs = [r for lst in agg["per_strategy"].values() for r in lst]
    if not runs:
        raise ExperimentError(f"no finished runs found in {directory}")
    seed_program = agg["experiment"]["base_config"]["seed_program"]
    dev = [r["best"]["dev_fitness"] for r in runs]
    test = [r["best"]["test_fitness"] for r in runs if r["best"]["test_fitness"] is not None]
    return seed_program, {
        "runs": len(runs), "proposals": sum(r["counts"]["proposals"] for r in runs),
        "improvements": sum(r["counts"]["improvements"] for r in runs),
        "best_dev_mean": statistics.fmean(dev), "best_test_mean": statistics.fmean(test) if test else None,
        "source": f"{directory}",
    }


def _instances_json(instance_set) -> dict:
    return {"name": instance_set.name,
            "instances": [{"n": len(pts), "points": [[x, y] for x, y in pts]} for pts in instance_set.instances]}


def _baselines(cfg: SearchConfig) -> dict:
    dev, test = cfg.instance_sets()
    out = {}
    for name in REFERENCES:
        source = load_tsp_seed_source(name)
        out[name] = {
            "dev": evaluate(source, dev, limits=cfg.limits, keep_tours=True).to_dict(),
            "test": evaluate(source, test, limits=cfg.limits, keep_tours=True).to_dict(),
        }
    return out


def _export_experiment(exp: Experiment) -> tuple[dict, dict]:
    archive = exp.archive()
    summary = json.loads((exp.dir / "summary.json").read_text(encoding="utf-8"))
    final = json.loads((exp.dir / "final.json").read_text(encoding="utf-8"))
    turns, running = [], None
    for p in archive:
        tdir = exp.turn_dir(p.iteration)
        record = None
        if (tdir / "eval_dev.json").exists():
            record = json.loads((tdir / "eval_dev.json").read_text(encoding="utf-8"))
        prompt = response = None
        hashes = {}
        for name in ("prompt.md", "response.md", "candidate.py", "eval_dev.json"):
            if (tdir / name).exists():
                hashes[name] = _sha_file(tdir / name)
        if p.iteration > 0:
            prompt, response = _read(tdir / "prompt.md"), _read(tdir / "response.md")
        improved = False
        if p.is_valid:
            if running is None:
                running = p.fitness
            elif p.fitness < running - EPS:  # type: ignore[operator]
                running, improved = p.fitness, True
        turns.append({
            "turn": p.iteration, "program_id": p.id, "parent_id": p.parent_id, "status": p.status,
            "error": p.error, "description": p.description, "fitness": p.fitness, "by_size": p.by_size,
            "mean_seconds": p.mean_seconds, "duplicate_of": p.duplicate_of, "hint": p.info.get("hint"),
            "prompt": prompt, "response": response, "code": p.source,
            "eval": record["eval"] if record else None, "note": record.get("note") if record else None,
            "improved": improved, "best_so_far": running, "hashes": hashes,
        })
    doc = {
        "schema_version": SCHEMA_VERSION, "id": exp.id, "title": exp.meta["title"], "meta": exp.meta,
        "config": exp.config.to_dict(), "turns": turns, "curve": summary["curve"],
        "summary": {"counts": summary["counts"], "seed": summary["seed"], "best": summary["best"]},
        "final": final, "evidence": f"evidence/{exp.id}/",
    }
    card = {
        "id": exp.id, "title": exp.meta["title"], "site": exp.meta["site"], "model": exp.meta["model"],
        "seed_program": exp.meta["seed_program"], "hints": exp.meta["hints"],
        "proposals": summary["counts"]["proposals"], "improvements": summary["counts"]["improvements"],
        "valid": summary["counts"]["valid"], "invalid": summary["counts"]["invalid"],
        "duplicate": summary["counts"]["duplicate"],
        "seed_dev": summary["seed"]["dev_fitness"], "best_dev": summary["best"]["dev_fitness"],
        "seed_test": summary["seed"]["test_fitness"], "best_test": summary["best"]["test_fitness"],
    }
    return doc, card


def export_experiments(base: str | Path, out_dir: str | Path, ids: list[str] | None = None,
                       blind_dirs: list[str] | None = None, copy_evidence: bool = True) -> list[str]:
    base, out_dir = Path(base), Path(out_dir)
    if ids:
        exps = [Experiment.open(base, i) for i in ids]
    else:
        exps = [Experiment(p.parent) for p in sorted(base.glob("*/meta.json"))]
    skipped = [e.id for e in exps if not e.finalized]
    exps = [e for e in exps if e.finalized]
    if not exps:
        raise ExperimentError("no finalized experiments to export. Run: loopforge exp finalize <id>")
    first = exps[0].config
    for e in exps[1:]:
        if (e.config.sizes, e.config.per_size) != (first.sizes, first.per_size):
            raise ExperimentError(f"{e.id} uses different instance sizes than {exps[0].id}; they cannot share one data set.")

    blind = dict(BLIND_FROM_RESULTS_MD)
    for directory in blind_dirs or []:
        seed_program, summary = summarize_blind(directory)
        blind[seed_program] = summary

    dev, test = first.instance_sets()
    _write(out_dir / "instances.json", _dumps({"schema_version": SCHEMA_VERSION, "dev": _instances_json(dev),
                                                "test": _instances_json(test)}, separators=(",", ":")))
    _write(out_dir / "baselines.json", _dumps({"schema_version": SCHEMA_VERSION, "references": _baselines(first),
                                                "blind_mutation": blind}, separators=(",", ":")))
    cards = []
    for e in exps:
        doc, card = _export_experiment(e)
        card["blind_mutation"] = blind.get(e.meta["seed_program"])
        cards.append(card)
        _write(out_dir / "experiments" / f"{e.id}.json", _dumps(doc, separators=(",", ":")))
        if copy_evidence:
            shutil.copytree(e.dir, out_dir.parent / "evidence" / e.id, dirs_exist_ok=True)
    _write(out_dir / "index.json", _dumps({"schema_version": SCHEMA_VERSION, "commit": _git_commit(),
                                            "experiments": cards}, indent=1) + "\n")
    if skipped:
        print(f"Skipped (not finalized): {', '.join(skipped)}")
    return [e.id for e in exps]


# ---------------------------------------------------------------- command-line glue


def _short(text: str | None, n: int = 70) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 3] + "..."


def cmd_new(args: argparse.Namespace) -> int:
    sizes = tuple(int(s) for s in args.sizes.split(",") if s.strip())
    exp = create_experiment(
        args.dir, args.id, seed_program=args.seed_program, model=args.model, site=args.site,
        title=args.title or "", hints=args.hints, max_turns=args.max_turns, settings=args.settings,
        notes=args.notes or "", sizes=sizes, per_size=args.per_size, time_limit=args.time_limit,
    )
    seed = exp.archive().get("p0000")
    print(f"Created {exp.dir}")
    print(f"Seed {args.seed_program}: dev fitness {seed.fitness:.4f}. Up to {exp.max_turns} turns. Hints: {'on' if args.hints else 'off'}.")
    print(f"Time limit: {_seconds(args.time_limit)} per instance (the prompt tells the AI this).")
    print(f"Recorded settings: {args.settings!r}. If that is not what you will actually do, delete the folder and rerun with --settings.")
    print(f"\nNext: loopforge exp prompt {exp.id}")
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    exp = Experiment.open(args.dir, args.id)
    turn, path, fresh = make_prompt(exp)
    resp = exp.turn_dir(turn) / "response.md"
    print(f"{'Wrote' if fresh else 'Prompt already exists:'} {path}  (turn {turn} of {exp.max_turns})")
    if args.show:
        print("\n" + _read(path))
    print(
        "\nNow:\n"
        f"  1. Open {path} in VS Code, select ALL, copy.\n"
        f"  2. Start a NEW chat on {exp.meta['site']} ({exp.meta['model']}). Turn off code execution/tools and memory.\n"
        "  3. Paste the prompt as your first and only message. Do not add anything. Do not edit the prompt.\n"
        "  4. Copy the AI's WHOLE reply (use the reply's Copy button).\n"
        f"  5. Create {resp} , paste the reply, save as UTF-8. Do not edit it.\n"
        "  6. Read the code in it. If it imports os/subprocess/socket or touches files, still ingest it:\n"
        "     the safety check will reject and record it. Do not run it yourself.\n"
        f"  7. Run: loopforge exp ingest {exp.id}"
    )
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    exp = Experiment.open(args.dir, args.id)
    print("Checking and running the candidate in the sandbox (a few seconds) ...")
    program, improved = ingest_turn(exp)
    print(f"\nTurn {program.iteration}: {program.id} -> {program.status.upper()}")
    if program.description:
        print(f"  AI's description: {program.description}")
    if program.is_valid:
        parent = exp.archive().get(program.parent_id)  # type: ignore[arg-type]
        print(f"  dev fitness {program.fitness:.4f} (parent {parent.fitness:.4f}; 2-opt = 1.0000)")
        print("  NEW BEST!" if improved else "  not better than the best so far.")
    elif program.status == DUPLICATE:
        print(f"  identical to {program.duplicate_of}; recorded, costs a turn, not re-evaluated.")
    else:
        print(f"  reason: {program.error}")
    used = program.iteration
    if used >= exp.max_turns:
        print(f"\nAll {exp.max_turns} turns used. Next: loopforge exp finalize {exp.id}")
    else:
        print(f"\n{used} of {exp.max_turns} turns used. Next: loopforge exp prompt {exp.id}   (or finalize early)")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    exp = Experiment.open(args.dir, args.id)
    archive = exp.archive()
    m = exp.meta
    print(f"{exp.id}: {m['title']}\n  {m['site']} / {m['model']}, seed {m['seed_program']}, hints {'on' if m['hints'] else 'off'}, "
          f"{len(archive) - 1} of {exp.max_turns} turns used, {'FINALIZED' if exp.finalized else 'open'}\n")
    print(f"{'turn':<5}{'id':<7}{'status':<11}{'dev fitness':<13}note")
    print("-" * 78)
    for p in archive:
        fit = f"{p.fitness:.4f}" if p.fitness is not None else "-"
        note = p.description if p.is_valid or p.status == DUPLICATE else (p.error or "")
        print(f"{p.iteration:<5}{p.id:<7}{p.status:<11}{fit:<13}{_short(note)}")
    best = archive.best()
    print(f"\nBest so far: {best.id} at {best.fitness:.4f} (seed {archive.get('p0000').fitness:.4f}, 2-opt = 1.0000)")  # type: ignore[union-attr]
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    exp = Experiment.open(args.dir, args.id)
    s = finalize_experiment(exp)
    c = s["counts"]
    print(f"Held-out test fitness: seed {s['seed']['test_fitness']} -> best {s['best']['test_fitness']}")
    print(f"Dev fitness: seed {s['seed']['dev_fitness']:.4f} -> best {s['best']['dev_fitness']:.4f}")
    print(f"{c['valid']} valid, {c['invalid']} invalid, {c['duplicate']} duplicate; {c['improvements']} improvements")
    print(f"Wrote {exp.dir / 'final.json'}, summary.json and best.py. This experiment is now closed.")
    print(f"Try: loopforge report {exp.dir}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    done = export_experiments(args.dir, args.out, args.ids or None, args.blind, copy_evidence=not args.no_evidence)
    print(f"Exported {len(done)} experiment(s) to {args.out}: {', '.join(done)}")
    return 0


def _guard(fn):
    def inner(args: argparse.Namespace) -> int:
        try:
            return fn(args)
        except ExperimentError as exc:
            print(f"\n{exc}", file=sys.stderr)
            return 2
    return inner


def register(sub) -> None:
    """Add the ``exp`` command group to the main parser (called from cli.py)."""
    p = sub.add_parser("exp", help="manual experiments with an AI website (new, prompt, ingest, status, finalize, export)")
    e = p.add_subparsers(dest="exp_command", required=True)

    def common(q, with_id=True):
        if with_id:
            q.add_argument("id", help="experiment id, e.g. e1-nn-cold")
        q.add_argument("--dir", default=DEFAULT_DIR, help="experiments folder (default: experiments)")

    q = e.add_parser("new", help="create an experiment and score its seed")
    common(q)
    q.add_argument("--seed-program", default="nearest_neighbor", choices=tsp_seed_names())
    q.add_argument("--model", required=True, help='exact model name as shown on the site, e.g. "GPT-5 (free)"')
    q.add_argument("--site", required=True, help="website, e.g. ChatGPT or Claude")
    q.add_argument("--title", help="short human title shown in the demo")
    q.add_argument("--hints", action="store_true", help="add a TSP-specific suggestion to each prompt")
    q.add_argument("--max-turns", type=int, default=6)
    q.add_argument("--settings", default=DEFAULT_SETTINGS, help="how the chat was configured (recorded as evidence)")
    q.add_argument("--notes", help="anything worth saying about this experiment")
    q.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES))
    q.add_argument("--per-size", type=int, default=DEFAULT_PER_SIZE)
    q.add_argument("--time-limit", type=float, default=DEFAULT_TIME_LIMIT,
                   help="seconds allowed per instance (default 10; the prompt states it)")
    q.set_defaults(func=_guard(cmd_new))

    q = e.add_parser("prompt", help="write the next prompt to paste into a new chat")
    common(q)
    q.add_argument("--show", action="store_true", help="also print the prompt here")
    q.set_defaults(func=_guard(cmd_prompt))

    q = e.add_parser("ingest", help="check, run and record the reply you saved as response.md")
    common(q)
    q.set_defaults(func=_guard(cmd_ingest))

    q = e.add_parser("status", help="show the turns so far")
    common(q)
    q.set_defaults(func=_guard(cmd_status))

    q = e.add_parser("finalize", help="score the best program on the held-out test set (once)")
    common(q)
    q.set_defaults(func=_guard(cmd_finalize))

    q = e.add_parser("export", help="write static JSON (+ evidence copies) for the web replay")
    q.add_argument("ids", nargs="*", help="experiment ids (default: all finalized ones)")
    q.add_argument("--dir", default=DEFAULT_DIR)
    q.add_argument("--out", default="web/public/data")
    q.add_argument("--blind", action="append", help="an offline `loopforge experiment` folder to use as the blind-mutation baseline (repeatable)")
    q.add_argument("--no-evidence", action="store_true", help="do not copy the raw experiment folders")
    q.set_defaults(func=_guard(cmd_export))
