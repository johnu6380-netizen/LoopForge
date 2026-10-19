"""Tests for the manual-experiment workflow. No network, no AI: replies are written by the tests."""

import json

import pytest

from loopforge.archive import DUPLICATE, INVALID, VALID
from loopforge.cli import main
from loopforge.evaluator import evaluate
from loopforge.manual import (
    Experiment, ExperimentError, create_experiment, export_experiments, finalize_experiment,
    ingest_turn, make_prompt,
)
from loopforge.runlog import load_run
from loopforge.safety import lint_source
from loopforge.seeds import load_tsp_seed_source, tsp_seed_names
from loopforge.tasks.tsp import make_instance_set, tour_length, validate_tour

TINY = dict(sizes=(8, 14), per_size=2)
TWO_OPT = load_tsp_seed_source("two_opt")
GARBAGE = "def solve(points):\n    return [0] * len(points)\n"


def reply(code=TWO_OPT, desc="add 2-opt"):
    return f"Here you go.\nDESCRIPTION: {desc}\n```python\n{code}\n```\nHope it helps!"


def new(tmp_path, exp_id="e1", **kw):
    kw.setdefault("seed_program", "nearest_neighbor")
    return create_experiment(tmp_path, exp_id, model="test-model", site="test-site", **TINY, **kw)


def do_turn(exp, text):
    """prompt -> paste the reply -> ingest, the way a person would."""
    make_prompt(exp)
    turn = len(exp.archive())
    (exp.turn_dir(turn) / "response.md").write_text(text, encoding="utf-8")
    return ingest_turn(exp)


# ---------------------------------------------------------------- evaluator addition


def test_keep_tours_returns_valid_tours_and_is_off_by_default():
    instances = make_instance_set("t", base_seed=3, sizes=(8, 14), per_size=1)
    src = load_tsp_seed_source("nearest_neighbor")
    plain = evaluate(src, instances)
    assert all(i.tour is None for i in plain.instances)
    kept = evaluate(src, instances, keep_tours=True)
    assert kept.fitness == pytest.approx(plain.fitness)
    for points, inst in zip(instances.instances, kept.instances):
        assert validate_tour(inst.tour, len(points))
        assert inst.length == pytest.approx(tour_length(points, inst.tour))


# ---------------------------------------------------------------- safety pre-check


def test_built_in_seeds_pass_the_safety_check():
    for name in tsp_seed_names():
        assert lint_source(load_tsp_seed_source(name)) == [], name


@pytest.mark.parametrize(
    "code, fragment",
    [
        ("import os\ndef solve(p):\n    return list(range(len(p)))", "'os'"),
        ("from subprocess import run\ndef solve(p):\n    return []", "'subprocess'"),
        ("import socket\ndef solve(p):\n    return []", "'socket'"),
        ("def solve(p):\n    open('x')\n    return []", "'open'"),
        ("def solve(p):\n    eval('1')\n    return []", "'eval'"),
        ("def solve(p):\n    return getattr(p, 'x')", "'getattr'"),
        ("def solve(p):\n    return p.__class__", "__class__"),
        ("def solve(p):\n    return __builtins__", "__builtins__"),
        ("def solve(p):\n    try:\n        raise ValueError\n    except ValueError as e:\n        return e.__traceback__.tb_frame", "tb_frame"),
        ("def solve(p):\n    return '{0.__class__}'.format(p)", "format string"),
    ],
)
def test_unsafe_programs_are_flagged(code, fragment):
    problems = lint_source(code)
    assert problems and any(fragment in line for line in problems)


def test_ordinary_code_with_classes_and_stdlib_is_not_flagged():
    code = (
        "import math, random, itertools, heapq\n"
        "class Helper:\n"
        "    def __init__(self, n):\n"
        "        self.n = n\n"
        "def solve(points):\n"
        "    h = Helper(len(points))\n"
        "    return list(range(h.n))\n"
    )
    assert lint_source(code) == []


# ---------------------------------------------------------------- creating and prompting


def test_new_experiment_scores_the_seed_and_writes_run_files(tmp_path):
    exp = new(tmp_path)
    for name in ("meta.json", "config.json", "programs.jsonl"):
        assert (exp.dir / name).exists(), name
    seed = exp.archive().get("p0000")
    assert seed.status == VALID and seed.fitness > 1.0
    record = json.loads((exp.dir / "turn-00" / "eval_dev.json").read_text(encoding="utf-8"))
    assert all(i["tour"] for i in record["eval"]["instances"])
    with pytest.raises(ExperimentError, match="already exists"):
        new(tmp_path)
    with pytest.raises(ExperimentError, match="unknown seed"):
        new(tmp_path, "e2", seed_program="nope")


def test_prompt_contains_the_parent_and_is_never_regenerated(tmp_path):
    exp = new(tmp_path)
    turn, path, fresh = make_prompt(exp)
    text = path.read_text(encoding="utf-8")
    assert fresh and turn == 1
    assert text.startswith("Answer directly") and "def solve" in text and "## Task" in text
    assert "Suggested direction" not in text  # hints are off
    path.write_text(text + "\nEDITED", encoding="utf-8")
    again = make_prompt(exp)
    assert again[2] is False and path.read_text(encoding="utf-8").endswith("EDITED")


def test_time_limit_defaults_to_10_seconds_is_stored_and_stated_in_the_prompt(tmp_path):
    exp = new(tmp_path)
    assert exp.config.limits.per_instance_seconds == 10.0
    assert exp.meta["time_limit_seconds"] == 10.0
    text = make_prompt(exp)[1].read_text(encoding="utf-8")
    assert "takes more than 10 seconds on an instance" in text and "about one" not in text
    reopened = Experiment.open(tmp_path, "e1")  # the limit survives a round trip through config.json
    assert reopened.config.limits.per_instance_seconds == 10.0


def test_custom_time_limit_is_used_and_validated(tmp_path):
    exp = new(tmp_path, time_limit=1)
    assert "takes more than 1 second on an instance" in make_prompt(exp)[1].read_text(encoding="utf-8")
    with pytest.raises(ExperimentError, match="time-limit"):
        new(tmp_path, "bad", time_limit=0)
    with pytest.raises(ExperimentError, match="time-limit"):
        new(tmp_path, "bad2", time_limit=600)


def test_hints_are_deterministic_per_experiment_and_turn(tmp_path):
    a = new(tmp_path / "a", hints=True)
    b = new(tmp_path / "b", hints=True)
    pa = make_prompt(a)[1].read_text(encoding="utf-8")
    pb = make_prompt(b)[1].read_text(encoding="utf-8")
    assert "Suggested direction" in pa and pa == pb


def test_next_parent_follows_the_hill_climb_rule(tmp_path):
    exp = new(tmp_path)
    do_turn(exp, reply())  # p0001 = 2-opt, a big improvement
    make_prompt(exp)
    meta = json.loads((exp.turn_dir(2) / "prompt.json").read_text(encoding="utf-8"))
    assert meta["parent_id"] == "p0001"
    do_turn(exp, reply(GARBAGE, "broken"))  # p0002 invalid: parent must stay p0001
    make_prompt(exp)
    meta = json.loads((exp.turn_dir(3) / "prompt.json").read_text(encoding="utf-8"))
    assert meta["parent_id"] == "p0001"


def test_failed_attempts_appear_in_the_next_prompt(tmp_path):
    exp = new(tmp_path)
    do_turn(exp, reply(GARBAGE, "broken"))
    text = make_prompt(exp)[1].read_text(encoding="utf-8")
    assert "Recent failed attempts" in text and "more than once" in text


# ---------------------------------------------------------------- ingesting


def test_valid_improvement_is_recorded_with_tours_and_files(tmp_path):
    exp = new(tmp_path)
    program, improved = do_turn(exp, reply())
    assert program.status == VALID and improved and program.parent_id == "p0000"
    assert program.fitness < exp.archive().get("p0000").fitness
    assert program.proposer == "manual" and program.description == "add 2-opt"
    tdir = exp.turn_dir(1)
    for name in ("prompt.md", "prompt.json", "response.md", "candidate.py", "eval_dev.json"):
        assert (tdir / name).exists(), name
    record = json.loads((tdir / "eval_dev.json").read_text(encoding="utf-8"))
    assert record["status"] == VALID and all(i["tour"] for i in record["eval"]["instances"])
    assert len((exp.dir / "programs.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_wrong_answers_unusable_replies_and_unsafe_code_are_recorded_as_failures(tmp_path):
    exp = new(tmp_path)
    bad, improved = do_turn(exp, reply(GARBAGE))
    assert bad.status == INVALID and "more than once" in bad.error and not improved
    unusable, _ = do_turn(exp, "I'm sorry, I can't help with that.")
    assert unusable.status == INVALID and "unusable reply" in unusable.error
    unsafe, _ = do_turn(exp, reply("import os\ndef solve(points):\n    return list(range(len(points)))\n"))
    assert unsafe.status == INVALID and "safety pre-check" in unsafe.error and "'os'" in unsafe.error
    record = json.loads((exp.turn_dir(3) / "eval_dev.json").read_text(encoding="utf-8"))
    assert record["eval"] is None  # rejected code was never run
    assert exp.archive().best().id == "p0000"


def test_duplicates_cost_a_turn_but_are_not_reevaluated(tmp_path):
    exp = new(tmp_path)
    first, _ = do_turn(exp, reply())
    second, improved = do_turn(exp, reply(TWO_OPT.replace("def solve(points):", "def solve(points):  # same")))
    assert second.status == DUPLICATE and second.duplicate_of == first.id and not improved


def test_non_ascii_replies_are_handled(tmp_path):
    exp = new(tmp_path)
    code = TWO_OPT.replace("import math", "# improved \u2192 faster \u2014 caf\u00e9\nimport math", 1)
    program, _ = do_turn(exp, reply(code))
    assert program.status == VALID
    assert "\u2192" in (exp.turn_dir(1) / "candidate.py").read_text(encoding="utf-8")


def test_nondeterministic_candidates_are_rejected(tmp_path):
    random_start = TWO_OPT.replace(
        "    tour = _nearest_neighbor(points)\n",
        "    import random\n    tour = list(range(n))\n    random.shuffle(tour)\n",
    )
    exp = create_experiment(tmp_path, "nd", model="m", site="s", seed_program="nearest_neighbor",
                            sizes=(40,), per_size=3)
    program, improved = do_turn(exp, reply(random_start))
    assert program.status == INVALID and "non-deterministic" in program.error and not improved


def test_missing_or_empty_response_and_budget_limits(tmp_path):
    exp = new(tmp_path, max_turns=1)
    with pytest.raises(ExperimentError, match="no prompt"):
        ingest_turn(exp)
    make_prompt(exp)
    with pytest.raises(ExperimentError, match="paste"):
        ingest_turn(exp)
    (exp.turn_dir(1) / "response.md").write_text("   \n", encoding="utf-8")
    with pytest.raises(ExperimentError, match="empty"):
        ingest_turn(exp)
    (exp.turn_dir(1) / "response.md").write_text(reply(), encoding="utf-8")
    ingest_turn(exp)
    with pytest.raises(ExperimentError, match="turns are used"):
        make_prompt(exp)
    with pytest.raises(ExperimentError, match="turns are used"):
        ingest_turn(exp)


# ---------------------------------------------------------------- finalize


def test_finalize_scores_the_test_set_once_and_closes_the_experiment(tmp_path):
    exp = new(tmp_path)
    do_turn(exp, reply())
    do_turn(exp, reply(GARBAGE))
    summary = finalize_experiment(exp)
    assert summary["best"]["id"] == "p0001"
    assert summary["best"]["test_fitness"] < summary["seed"]["test_fitness"]
    assert summary["counts"] == {"proposals": 2, "valid": 1, "invalid": 1, "duplicate": 0, "improvements": 1}
    assert summary["curve"][0] > summary["curve"][-1]
    assert exp.finalized and (exp.dir / "best.py").exists()
    with pytest.raises(ExperimentError, match="already finalized"):
        finalize_experiment(exp)
    with pytest.raises(ExperimentError, match="finalized"):
        make_prompt(exp)
    run = load_run(exp.dir)  # works with the existing `loopforge report`
    assert run.summary["best"]["id"] == "p0001" and len(run.programs) == 3


def test_finalize_needs_a_turn_and_refuses_a_dangling_prompt(tmp_path):
    exp = new(tmp_path)
    with pytest.raises(ExperimentError, match="no turns"):
        finalize_experiment(exp)
    do_turn(exp, reply())
    make_prompt(exp)  # prompt for turn 2, never answered
    with pytest.raises(ExperimentError, match="no ingested reply"):
        finalize_experiment(exp)


# ---------------------------------------------------------------- export


def test_export_writes_replay_data_whose_tours_recompute(tmp_path):
    exp = new(tmp_path / "experiments")
    do_turn(exp, reply())
    do_turn(exp, reply(GARBAGE))
    finalize_experiment(exp)
    out = tmp_path / "web" / "public" / "data"
    assert export_experiments(tmp_path / "experiments", out) == ["e1"]

    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    card = index["experiments"][0]
    assert card["id"] == "e1" and card["improvements"] == 1 and card["blind_mutation"]["improvements"] == 0
    inst = json.loads((out / "instances.json").read_text(encoding="utf-8"))
    base = json.loads((out / "baselines.json").read_text(encoding="utf-8"))
    assert base["references"]["two_opt"]["dev"]["fitness"] == pytest.approx(1.0)
    data = json.loads((out / "experiments" / "e1.json").read_text(encoding="utf-8"))
    assert [t["status"] for t in data["turns"]] == [VALID, VALID, INVALID]
    assert data["turns"][1]["prompt"] and data["turns"][1]["response"] and data["turns"][1]["hashes"]["response.md"]

    # The browser-side "recompute" check: every stored length must match the stored tour and points.
    for t in data["turns"]:
        if t["eval"]:
            for points, r in zip(inst["dev"]["instances"], t["eval"]["instances"]):
                if r["tour"]:
                    pts = [tuple(p) for p in points["points"]]
                    assert tour_length(pts, r["tour"]) == pytest.approx(r["length"])
    assert (tmp_path / "web" / "public" / "evidence" / "e1" / "turn-01" / "response.md").exists()


def test_export_skips_unfinalized_experiments(tmp_path):
    exp = new(tmp_path)
    do_turn(exp, reply())
    with pytest.raises(ExperimentError, match="no finalized"):
        export_experiments(tmp_path, tmp_path / "out")


# ---------------------------------------------------------------- command line


def test_cli_end_to_end(tmp_path, capsys):
    base = str(tmp_path / "experiments")
    common = ["--dir", base]
    assert main(["exp", "new", "c1", "--model", "m", "--site", "s", "--sizes", "8,14", "--per-size", "2", *common]) == 0
    assert main(["exp", "prompt", "c1", *common]) == 0
    assert "Do not edit" in capsys.readouterr().out
    exp = Experiment.open(base, "c1")
    (exp.turn_dir(1) / "response.md").write_text(reply(), encoding="utf-8")
    assert main(["exp", "ingest", "c1", *common]) == 0
    assert "NEW BEST" in capsys.readouterr().out
    assert main(["exp", "status", "c1", *common]) == 0
    assert "p0001" in capsys.readouterr().out
    assert main(["exp", "finalize", "c1", *common]) == 0
    assert main(["exp", "finalize", "c1", *common]) == 2  # second time is refused
    assert main(["report", str(exp.dir)]) == 0
    out = capsys.readouterr().out
    assert "Held-out test fitness" in out and "iter    1" in out
    assert main(["exp", "export", "--dir", base, "--out", str(tmp_path / "web" / "public" / "data")]) == 0


def test_cli_errors_are_polite_not_tracebacks(tmp_path, capsys):
    assert main(["exp", "prompt", "missing", "--dir", str(tmp_path)]) == 2
    assert "no experiment" in capsys.readouterr().err
