import json
import math
import random

import pytest

from loopforge.archive import DUPLICATE, INVALID, VALID, Archive, Program
from loopforge.evaluator import evaluate
from loopforge.proposers import ScriptedProposer
from loopforge.runlog import RunLogger, load_run, unique_run_dir
from loopforge.search import (
    EvolveStrategy, HillClimbStrategy, RandomStrategy, Search, SearchConfig, make_strategy,
)
from loopforge.seeds import load_tsp_seed_source

TINY = dict(sizes=(8, 14), per_size=2)  # keeps every test fast
TWO_OPT = load_tsp_seed_source("two_opt")
GARBAGE = "def solve(points):\n    return [0] * len(points)\n"
RANDOM_START_2OPT = TWO_OPT.replace(
    "    tour = _nearest_neighbor(points)\n",
    "    import random\n    tour = list(range(n))\n    random.shuffle(tour)\n",
)


def cfg(**kw):
    return SearchConfig(**{**TINY, "budget": 3, **kw})


def run(proposer, **kw):
    return Search(cfg(**kw), proposer).run()


# ---------- the loop ----------


def test_finds_an_improvement_and_records_lineage():
    result = run(ScriptedProposer([TWO_OPT]), budget=1)
    best = result.archive.best()
    assert best.id == "p0001" and best.parent_id == "p0000"
    assert best.fitness < result.archive.get("p0000").fitness
    assert result.summary["counts"]["improvements"] == 1
    assert result.summary["best"]["lineage"] == ["p0000", "p0001"]


def test_budget_is_exactly_the_number_of_proposals():
    result = run(ScriptedProposer([GARBAGE, TWO_OPT, GARBAGE]), budget=3)
    assert len(result.archive) == 4  # seed + 3 proposals
    assert [p.iteration for p in result.archive] == [0, 1, 2, 3]
    assert len(result.summary["curve"]) == 4


def test_invalid_proposals_are_recorded_not_dropped():
    result = run(ScriptedProposer([GARBAGE, "def solve(p) return", "x = 1"]), budget=3)
    programs = list(result.archive)[1:]
    assert all(p.status == INVALID and p.error for p in programs)
    assert "more than once" in programs[0].error
    assert "SyntaxError" in programs[1].error
    assert "solve" in programs[2].error
    assert result.summary["counts"]["invalid"] == 3


def test_duplicates_cost_budget_but_are_not_reevaluated():
    calls = []

    def counting_eval(source, instance_set, **kw):
        calls.append(instance_set.name)
        return evaluate(source, instance_set, **kw)

    reformatted = TWO_OPT.replace("def solve(points):", "def solve(points):  # same thing")
    search = Search(cfg(budget=3, verify_new_best=False),
                    ScriptedProposer([TWO_OPT, TWO_OPT, reformatted]), evaluate_fn=counting_eval)
    result = search.run()
    statuses = [p.status for p in result.archive]
    assert statuses == [VALID, VALID, DUPLICATE, DUPLICATE]
    assert result.archive.get("p0002").duplicate_of == "p0001"
    # evaluations: seed(dev) + two_opt(dev) + final best(test) + seed(test)
    assert calls.count("dev") == 2
    assert result.summary["counts"]["duplicate"] == 2


def test_proposer_failure_counts_against_budget():
    result = run(ScriptedProposer([]), budget=2)  # raises ProposalError every time
    programs = list(result.archive)[1:]
    assert [p.status for p in programs] == [INVALID, INVALID]
    assert "proposal failed" in programs[0].error


def test_seed_program_must_be_valid(monkeypatch):
    monkeypatch.setattr("loopforge.search.load_tsp_seed_source", lambda name: "x = 1")
    with pytest.raises(RuntimeError, match="invalid"):
        run(ScriptedProposer([]), budget=1)


def test_same_seed_gives_identical_runs():
    def sources(seed):
        r = Search(cfg(budget=12, seed=seed, strategy="evolve")).run()
        return [(p.source, p.status) for p in r.archive]

    assert sources(3) == sources(3)
    assert sources(3) != sources(4)


def test_summary_curve_never_gets_worse():
    result = run(ScriptedProposer([GARBAGE, TWO_OPT, GARBAGE]), budget=3)
    curve = result.summary["curve"]
    assert all(b <= a for a, b in zip(curve, curve[1:]))
    assert curve[-1] == result.summary["best"]["dev_fitness"]


# ---------- honesty guards ----------


def test_search_decisions_use_only_the_dev_set_until_the_final_step():
    seen = []

    def spy(source, instance_set, **kw):
        seen.append(instance_set.name)
        return evaluate(source, instance_set, **kw)

    Search(cfg(budget=4), ScriptedProposer([TWO_OPT, GARBAGE, TWO_OPT, GARBAGE]), evaluate_fn=spy).run()
    first_test = seen.index("test")
    assert "test" not in seen[:first_test]
    assert set(seen[first_test:]) == {"test"}  # nothing but test evaluations at the end
    assert seen[first_test:].count("test") <= 2  # best and seed, once each


def test_dev_and_test_sets_differ():
    dev, test = cfg().instance_sets()
    assert set(dev.instances).isdisjoint(set(test.instances))


def test_nondeterministic_candidates_are_rejected():
    # 2-opt from a random starting tour lands on different local optima each run.
    result = run(ScriptedProposer([RANDOM_START_2OPT]), budget=1, sizes=(40,), per_size=3)
    program = result.archive.get("p0001")
    assert program.status == INVALID
    assert "non-deterministic" in program.error
    assert result.archive.best().id == "p0000"


def test_nondeterminism_check_can_be_disabled():
    result = run(ScriptedProposer([RANDOM_START_2OPT]), budget=1, sizes=(40,), per_size=3,
                 verify_new_best=False)
    assert result.archive.get("p0001").status == VALID


def test_test_fitness_is_reported_for_seed_and_best():
    s = run(ScriptedProposer([TWO_OPT]), budget=1).summary
    assert s["best"]["test_fitness"] < s["seed"]["test_fitness"]
    assert s["best"]["dev_fitness"] < s["seed"]["dev_fitness"]


# ---------- strategies ----------


def archive_of(*fitnesses):
    a = Archive()
    for i, f in enumerate(fitnesses):
        a.add(Program(a.next_id(), None if i == 0 else "p0000", i, "", VALID if f is not None else INVALID, f))
    return a


def test_random_strategy_always_picks_the_seed():
    a = archive_of(1.5, 1.2, 1.1)
    s = RandomStrategy()
    assert {s.select(a, random.Random(i)).id for i in range(20)} == {"p0000"}


def test_hill_climb_follows_improvements_and_ties_but_not_regressions():
    s = HillClimbStrategy()
    seed = Program("p0000", None, 0, "", VALID, 1.5)
    s.observe(seed)
    better = Program("p0001", "p0000", 1, "", VALID, 1.2)
    worse = Program("p0002", "p0001", 2, "", VALID, 1.3)
    tie = Program("p0003", "p0001", 3, "", VALID, 1.2)
    bad = Program("p0004", "p0001", 4, "", INVALID)
    a = archive_of(1.5)
    for p, expect in [(better, "p0001"), (worse, "p0001"), (bad, "p0001"), (tie, "p0003")]:
        s.observe(p)
        assert s.select(a, random.Random(0)).id == expect


def test_evolve_picks_only_valid_programs_and_prefers_better_ones():
    a = archive_of(1.5, None, 1.4, None, 1.3, 1.2, 1.1, 1.6)
    s = EvolveStrategy(tournament_size=3)
    rng = random.Random(0)
    picks = [s.select(a, rng) for _ in range(600)]
    assert all(p.is_valid for p in picks)
    counts = {}
    for p in picks:
        counts[p.id] = counts.get(p.id, 0) + 1
    # With 6 valid programs and tournaments of 3, the best wins about 50% of the time, the
    # 4th-best about 5%, and the two worst can never win a tournament.
    assert counts["p0006"] > 3 * counts["p0002"]
    assert "p0007" not in counts and "p0000" not in counts


def test_evolve_handles_tiny_archives():
    a = archive_of(1.5)
    assert EvolveStrategy(5).select(a, random.Random(0)).id == "p0000"


def test_make_strategy():
    assert make_strategy(cfg(strategy="random")).name == "random"
    assert make_strategy(cfg(strategy="hill_climb")).name == "hill_climb"
    assert make_strategy(cfg(strategy="evolve")).name == "evolve"
    with pytest.raises(ValueError):
        make_strategy(cfg(strategy="nope"))


def test_evolve_actually_branches_from_good_programs():
    proposer = ScriptedProposer([TWO_OPT, GARBAGE, GARBAGE, GARBAGE, GARBAGE, GARBAGE])
    Search(cfg(budget=6, strategy="evolve", tournament_size=3), proposer).run()
    # once p0001 (2-opt) exists it wins nearly every tournament against the seed
    assert proposer.parents_seen.count("p0001") >= 3


# ---------- logging ----------


def test_run_logger_writes_a_replayable_log(tmp_path):
    run_dir = tmp_path / "r1"
    result = Search(cfg(budget=3), ScriptedProposer([GARBAGE, TWO_OPT, TWO_OPT]), logger=RunLogger(run_dir)).run()
    for name in ("config.json", "programs.jsonl", "summary.json", "best.py"):
        assert (run_dir / name).exists(), name
    loaded = load_run(run_dir)
    assert [p.to_dict() for p in loaded.programs] == [p.to_dict() for p in result.archive]
    assert loaded.summary["best"]["id"] == "p0002"
    assert loaded.config["strategy"] == "evolve"
    assert "def solve" in (run_dir / "best.py").read_text()


def test_log_files_are_strict_json(tmp_path):
    run_dir = tmp_path / "r2"
    Search(cfg(budget=2), ScriptedProposer([GARBAGE, TWO_OPT]), logger=RunLogger(run_dir)).run()
    for line in (run_dir / "programs.jsonl").read_text().splitlines():
        json.loads(line, parse_constant=lambda c: pytest.fail(f"non-standard JSON constant {c}"))
    json.loads((run_dir / "summary.json").read_text(),
               parse_constant=lambda c: pytest.fail(f"non-standard JSON constant {c}"))


def test_programs_are_logged_as_they_happen(tmp_path):
    run_dir = tmp_path / "r3"
    lengths = []

    def progress(i, budget, program, best):
        lengths.append(len((run_dir / "programs.jsonl").read_text().splitlines()))

    Search(cfg(budget=3), ScriptedProposer([GARBAGE, TWO_OPT, GARBAGE]), logger=RunLogger(run_dir),
           progress=progress).run()
    assert lengths == [2, 3, 4]  # seed + each proposal, flushed before the next one starts


def test_unique_run_dir(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a-2").mkdir()
    assert unique_run_dir(tmp_path, "a").name == "a-3"
    assert unique_run_dir(tmp_path, "b").name == "b"
