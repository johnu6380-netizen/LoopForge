"""The search loop.

One iteration: pick a parent from the archive -> ask the proposer for a new
program -> evaluate it in the sandbox -> record it. The *strategy* decides which
parent to pick; the *proposer* decides what the new program is. Keeping those two
separate lets us compare search strategies and proposers independently.

Honesty guards built into the loop:

* Budget = number of proposals, charged whether or not the proposal was valid,
  a duplicate, or failed outright. (An LLM call costs the same either way.)
* The search only ever sees the dev set. The held-out test set is evaluated once,
  at the very end, on the single best program, and never influences a decision.
* A program that becomes the new best is evaluated a second time. If its score
  changes (unseeded randomness, timing luck), it is rejected as non-deterministic.
* Proposals identical to an earlier program (ignoring comments and formatting)
  are not re-evaluated, but still cost budget.
"""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Protocol

from . import __version__
from .archive import DUPLICATE, INVALID, VALID, Archive, Program
from .evaluator import EvalResult, evaluate
from .proposers import ProposalError, Proposer, get_proposer
from .runlog import RunLogger
from .sandbox import SandboxLimits
from .seeds import load_tsp_seed_source
from .sourcetools import normalize_source, precheck, source_key
from .usage import summarize_usage
from .tasks.tsp import DEFAULT_PER_SIZE, DEFAULT_SIZES, InstanceSet, make_instance_set
from .tasks.tsp import DEV_BASE_SEED, TEST_BASE_SEED

EPS = 1e-12  # improvements smaller than this are treated as ties
VERIFY_TOLERANCE = 1e-9

# Search runs use a tighter per-instance limit than the sandbox default:
# the reference 2-opt needs about 5 ms, so 1 s is very generous.
SEARCH_LIMITS = SandboxLimits(per_instance_seconds=1.0)


@dataclass
class SearchConfig:
    strategy: str = "evolve"  # "random", "hill_climb" or "evolve"
    proposer: str = "mutation"
    budget: int = 200  # number of proposals
    seed: int = 0  # controls every random choice in the run
    seed_program: str = "nearest_neighbor"
    tournament_size: int = 3  # only used by "evolve"
    proposer_options: dict = field(default_factory=dict)  # provider, model, caps for "llm"; never secrets
    sizes: tuple[int, ...] = DEFAULT_SIZES
    per_size: int = DEFAULT_PER_SIZE
    verify_new_best: bool = True
    limits: SandboxLimits = field(default_factory=lambda: SEARCH_LIMITS)

    def instance_sets(self) -> tuple[InstanceSet, InstanceSet]:
        dev = make_instance_set("dev", DEV_BASE_SEED, tuple(self.sizes), self.per_size)
        test = make_instance_set("test", TEST_BASE_SEED, tuple(self.sizes), self.per_size)
        return dev, test

    def to_dict(self) -> dict:
        data = asdict(self)
        data["sizes"] = list(self.sizes)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SearchConfig":
        """Inverse of ``to_dict`` (also accepts a plain dict of overrides)."""
        values = dict(data)
        if "sizes" in values:
            values["sizes"] = tuple(values["sizes"])
        if isinstance(values.get("limits"), dict):
            values["limits"] = SandboxLimits(**values["limits"])
        return cls(**values)


# ---------------------------------------------------------------- strategies


class Strategy(Protocol):
    name: str

    def select(self, archive: Archive, rng: random.Random) -> Program: ...

    def observe(self, program: Program) -> None: ...


class RandomStrategy:
    """Always mutate the original seed. No memory: the weakest sensible baseline."""

    name = "random"

    def __init__(self) -> None:
        self._seed: Program | None = None

    def select(self, archive, rng):
        if self._seed is None:
            self._seed = next(iter(archive))
        return self._seed

    def observe(self, program):
        pass


class HillClimbStrategy:
    """Keep one current program; move to a child only if it is at least as good.

    Accepting ties lets the search drift across plateaus of equal-fitness edits,
    as in a standard (1+1) evolutionary algorithm.
    """

    name = "hill_climb"

    def __init__(self) -> None:
        self._current: Program | None = None

    def select(self, archive, rng):
        if self._current is None:
            self._current = archive.best()
        return self._current  # type: ignore[return-value]

    def observe(self, program):
        if not program.is_valid:
            return
        if self._current is None or program.fitness <= self._current.fitness + EPS:  # type: ignore[operator]
            self._current = program


class EvolveStrategy:
    """Tournament selection over every valid program found so far.

    Draw ``tournament_size`` valid programs at random and pick the best of them.
    Better programs are chosen more often, but weaker ones still get a chance, so
    the search keeps several lines of descent alive instead of one.
    """

    name = "evolve"

    def __init__(self, tournament_size: int = 3) -> None:
        self.tournament_size = tournament_size

    def select(self, archive, rng):
        pool = archive.valid()
        k = min(self.tournament_size, len(pool))
        contenders = rng.sample(pool, k)
        return min(contenders, key=lambda p: p.fitness)  # type: ignore[arg-type,return-value]

    def observe(self, program):
        pass


def make_strategy(config: SearchConfig) -> Strategy:
    if config.strategy == "random":
        return RandomStrategy()
    if config.strategy == "hill_climb":
        return HillClimbStrategy()
    if config.strategy == "evolve":
        return EvolveStrategy(config.tournament_size)
    raise ValueError(f"unknown strategy {config.strategy!r}; use random, hill_climb or evolve")


# ---------------------------------------------------------------- the loop


@dataclass
class RunResult:
    summary: dict
    archive: Archive


ProgressFn = Callable[[int, int, Program, "Program | None"], None]


class Search:
    def __init__(
        self,
        config: SearchConfig,
        proposer: Proposer | None = None,
        *,
        logger: RunLogger | None = None,
        progress: ProgressFn | None = None,
        evaluate_fn: Callable[..., EvalResult] | None = None,
    ) -> None:
        self.config = config
        self.proposer = proposer if proposer is not None else get_proposer(config.proposer, config.proposer_options)
        self.logger = logger
        self.progress = progress
        self._evaluate = evaluate_fn if evaluate_fn is not None else evaluate

    def _eval(self, source: str, instance_set: InstanceSet) -> EvalResult:
        return self._evaluate(source, instance_set, limits=self.config.limits)

    @staticmethod
    def _by_size(result: EvalResult) -> dict[str, float]:
        groups: dict[int, list[float]] = {}
        for inst in result.instances:
            if inst.valid and inst.ratio is not None:
                groups.setdefault(inst.n, []).append(inst.ratio)
        return {str(n): sum(v) / len(v) for n, v in sorted(groups.items())}

    def _program_from_result(self, pid, parent_id, iteration, source, result, description, proposer, info):
        if result.valid:
            return Program(
                id=pid, parent_id=parent_id, iteration=iteration, source=source, status=VALID,
                fitness=result.fitness, by_size=self._by_size(result), mean_seconds=result.mean_seconds,
                description=description, proposer=proposer, info=info,
            )
        return Program(
            id=pid, parent_id=parent_id, iteration=iteration, source=source, status=INVALID,
            mean_seconds=result.mean_seconds, error=result.error,
            description=description, proposer=proposer, info=info,
        )

    def run(self) -> RunResult:
        cfg = self.config
        started = time.perf_counter()
        rng = random.Random(cfg.seed)
        dev, test = cfg.instance_sets()
        archive = Archive()
        strategy = make_strategy(cfg)

        run_id = self.logger.directory.name if self.logger else f"{cfg.proposer}-{cfg.strategy}-s{cfg.seed}"
        if self.logger:
            self.logger.write_config({"run_id": run_id, "version": __version__, **cfg.to_dict()})

        def record(program: Program, key: str | None) -> None:
            archive.add(program, key)
            strategy.observe(program)
            if self.logger:
                self.logger.log_program(program)

        # --- iteration 0: the seed program ---
        seed_source = normalize_source(load_tsp_seed_source(cfg.seed_program))
        assert seed_source is not None
        seed_result = self._eval(seed_source, dev)
        if not seed_result.valid:
            raise RuntimeError(f"the seed program {cfg.seed_program!r} is invalid: {seed_result.error}")
        seed = self._program_from_result(
            archive.next_id(), None, 0, seed_source, seed_result,
            f"seed: {cfg.seed_program}", "seed", {},
        )
        record(seed, source_key(seed_source))

        best_fitness = seed.fitness
        curve = [best_fitness]
        improvements = 0

        # --- the loop ---
        made = 0
        stopped = None
        for iteration in range(1, cfg.budget + 1):
            if getattr(self.proposer, "exhausted", False):  # e.g. an LLM spending cap
                stopped = "proposer spending cap reached"
                break
            made += 1
            parent = strategy.select(archive, rng)
            pid = archive.next_id()
            try:
                proposal = self.proposer.propose(parent, archive, rng)
            except ProposalError as exc:
                program = Program(
                    id=pid, parent_id=parent.id, iteration=iteration, source="", status=INVALID,
                    error=f"proposal failed: {exc}", proposer=self.proposer.name,
                    info=getattr(exc, "info", {}),
                )
                record(program, None)
                curve.append(best_fitness)
                self._report(iteration, program, archive)
                continue

            source = proposal.source
            key = source_key(source)
            earlier = archive.lookup(key)

            if earlier is not None:
                program = Program(
                    id=pid, parent_id=parent.id, iteration=iteration, source=source, status=DUPLICATE,
                    fitness=earlier.fitness, by_size=dict(earlier.by_size), error=earlier.error,
                    description=proposal.description, proposer=self.proposer.name,
                    duplicate_of=earlier.id, info=proposal.info,
                )
            else:
                problem = precheck(source)
                if problem is not None:
                    program = Program(
                        id=pid, parent_id=parent.id, iteration=iteration, source=source, status=INVALID,
                        error=problem, description=proposal.description,
                        proposer=self.proposer.name, info=proposal.info,
                    )
                else:
                    result = self._eval(source, dev)
                    if result.valid and result.fitness < best_fitness - EPS and cfg.verify_new_best:
                        again = self._eval(source, dev)
                        if not again.valid or abs(again.fitness - result.fitness) > VERIFY_TOLERANCE:
                            second = f"{again.fitness:.6f}" if again.valid else "invalid"
                            result = EvalResult(
                                valid=False, fitness=float("inf"), mean_seconds=result.mean_seconds,
                                error=f"non-deterministic: scored {result.fitness:.6f}, then {second}",
                            )
                    program = self._program_from_result(
                        pid, parent.id, iteration, source, result,
                        proposal.description, self.proposer.name, proposal.info,
                    )

            record(program, key)
            if program.is_valid and program.fitness < best_fitness - EPS:  # type: ignore[operator]
                best_fitness = program.fitness
                improvements += 1
            curve.append(best_fitness)
            self._report(iteration, program, archive)

        # --- finish: the held-out test set is touched exactly once, here ---
        best = archive.best()
        assert best is not None
        test_best = self._eval(best.source, test)
        test_seed = test_best if best is seed else self._eval(seed.source, test)
        counts = archive.counts()
        summary = {
            "run_id": run_id,
            "version": __version__,
            "config": cfg.to_dict(),
            "seed": {
                "id": seed.id, "dev_fitness": seed.fitness,
                "test_fitness": test_seed.fitness if test_seed.valid else None,
            },
            "best": {
                "id": best.id, "iteration": best.iteration, "dev_fitness": best.fitness,
                "test_fitness": test_best.fitness if test_best.valid else None,
                "lineage": [p.id for p in archive.lineage(best.id)],
                "description": best.description,
            },
            "counts": {
                "proposals": made, "valid": counts[VALID] - 1,  # minus the seed
                "invalid": counts[INVALID], "duplicate": counts[DUPLICATE],
                "improvements": improvements,
            },
            "curve": curve,
            "stopped_early": stopped,
            "usage": summarize_usage(archive),
            "wall_seconds": time.perf_counter() - started,
        }
        if self.logger:
            self.logger.write_summary(summary)
            self.logger.write_best_source(best.source)
        return RunResult(summary, archive)

    def _report(self, iteration: int, program: Program, archive: Archive) -> None:
        if self.progress:
            self.progress(iteration, self.config.budget, program, archive.best())
