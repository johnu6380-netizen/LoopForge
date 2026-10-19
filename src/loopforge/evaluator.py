"""Scoring candidates on a TSP instance set.

Candidates run in a sandboxed subprocess by default (see ``sandbox.py``). The
sandbox only returns raw tours; *this* module validates them and computes every
score, so a candidate can never influence its own result beyond the tour it
returns.

Scoring
-------
For each instance we compute ``length / reference_length`` where the reference
is the 2-opt baseline. So:

* 1.00 means "as good as 2-opt"
* below 1.00 means "better than 2-opt"
* above 1.00 means worse

The candidate's fitness is the mean ratio over all instances (lower is better).
If *any* instance returns an invalid tour, crashes, or runs too slowly, the
whole candidate is invalid and gets fitness = infinity. No partial credit: a
heuristic that sometimes returns garbage is not a heuristic. Evaluation stops at
the first failure ("fail fast") since the outcome is already decided.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

from .sandbox import DEFAULT_LIMITS, RawRun, SandboxLimits, SandboxOutcome, run_in_sandbox
from .seeds import load_tsp_seed_source
from .tasks.tsp import InstanceSet, InvalidTour, tour_length, validate_tour


class CandidateError(Exception):
    """The candidate source could not be turned into a usable ``solve`` function."""


@dataclass(frozen=True)
class InstanceResult:
    n: int
    valid: bool
    length: float | None
    ratio: float | None  # length / reference length
    seconds: float
    error: str | None = None
    tour: list[int] | None = None  # only filled when evaluate(..., keep_tours=True)


@dataclass
class EvalResult:
    valid: bool
    fitness: float  # mean ratio vs reference; math.inf if invalid
    mean_seconds: float
    instances: list[InstanceResult] = field(default_factory=list)
    error: str | None = None
    sandbox_limits: list[str] = field(default_factory=list)  # protections that were active

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            # JSON has no infinity, so report invalid fitness as null.
            "fitness": self.fitness if math.isfinite(self.fitness) else None,
            "mean_seconds": self.mean_seconds,
            "error": self.error,
            "sandbox_limits": self.sandbox_limits,
            "instances": [vars(i) for i in self.instances],
        }


def compile_candidate(source: str) -> Callable:
    """Turn source into its ``solve`` function, IN-PROCESS and UNSANDBOXED.

    Only for trusted code (the built-in seeds). Never call this on LLM output.
    """
    namespace: dict = {"__name__": "candidate"}
    try:
        exec(compile(source, "<candidate>", "exec"), namespace)
    except Exception as exc:  # syntax errors, import errors, top-level crashes
        raise CandidateError(f"{type(exc).__name__}: {exc}") from exc
    solve = namespace.get("solve")
    if not callable(solve):
        raise CandidateError("source does not define a callable named 'solve'")
    return solve


_reference_cache: dict[str, list[float]] = {}


def reference_lengths(instance_set: InstanceSet) -> list[float]:
    """Tour lengths of the 2-opt reference on each instance (computed once, cached)."""
    key = f"{instance_set.name}:{len(instance_set)}:{hash(instance_set.instances)}"
    if key not in _reference_cache:
        solve = compile_candidate(load_tsp_seed_source("two_opt"))
        lengths = []
        for points in instance_set.instances:
            tour = validate_tour(solve([tuple(p) for p in points]), len(points))
            lengths.append(tour_length(points, tour))
        _reference_cache[key] = lengths
    return _reference_cache[key]


def _run_in_process(source: str, instances) -> SandboxOutcome:
    """Trusted-code path: same output shape as the sandbox, no isolation."""
    try:
        solve = compile_candidate(source)
    except CandidateError as exc:
        return SandboxOutcome(fatal=str(exc))
    outcome = SandboxOutcome()
    for i, points in enumerate(instances):
        start = time.perf_counter()
        try:
            tour = solve([tuple(p) for p in points])
            error = None
        except Exception as exc:
            tour, error = None, f"{type(exc).__name__}: {exc}"
        outcome.runs.append(RawRun(i, time.perf_counter() - start, tour, error))
        if error is not None:
            break
    return outcome


def _score(
    outcome: SandboxOutcome,
    instance_set: InstanceSet,
    references: list[float],
    time_limit: float | None,
    keep_tours: bool = False,
) -> EvalResult:
    """Validate raw tours and compute fitness. Nothing from the candidate is trusted."""
    results: list[InstanceResult] = []
    failure: str | None = None

    for run in outcome.runs:
        points = instance_set.instances[run.index]
        n = len(points)
        error = run.error
        if error is None:
            try:
                tour = validate_tour(run.tour, n)
            except InvalidTour as exc:
                error = f"invalid tour: {exc}"
        if error is None and time_limit is not None and run.seconds > time_limit:
            error = f"too slow: {run.seconds:.2f}s is over the {time_limit:.2f}s limit"

        if error is not None:
            results.append(InstanceResult(n, False, None, None, run.seconds, error))
            failure = f"instance {run.index} (n={n}) failed: {error}"
            break
        length = tour_length(points, tour)
        results.append(
            InstanceResult(
                n, True, length, length / references[run.index], run.seconds,
                tour=list(tour) if keep_tours else None,
            )
        )

    mean_seconds = sum(r.seconds for r in results) / len(results) if results else 0.0

    error = outcome.fatal or failure
    if error is None and len(results) != len(instance_set.instances):
        error = f"sandbox returned {len(results)} of {len(instance_set.instances)} results"
    if error is not None:
        return EvalResult(
            valid=False,
            fitness=math.inf,
            mean_seconds=mean_seconds,
            instances=results,
            error=error,
            sandbox_limits=outcome.limits_applied,
        )

    fitness = sum(r.ratio for r in results) / len(results)  # type: ignore[misc]
    return EvalResult(
        valid=True,
        fitness=fitness,
        mean_seconds=mean_seconds,
        instances=results,
        sandbox_limits=outcome.limits_applied,
    )


def evaluate(
    source: str,
    instance_set: InstanceSet,
    *,
    sandboxed: bool = True,
    limits: SandboxLimits = DEFAULT_LIMITS,
    keep_tours: bool = False,
) -> EvalResult:
    """Score candidate source on every instance in the set.

    ``sandboxed=False`` runs in this process and is only for trusted code.
    """
    references = reference_lengths(instance_set)
    if sandboxed:
        outcome = run_in_sandbox(source, instance_set.instances, limits)
        time_limit: float | None = limits.per_instance_seconds
    else:
        outcome = _run_in_process(source, instance_set.instances)
        time_limit = None
    return _score(outcome, instance_set, references, time_limit, keep_tours)
