import json

import pytest

from loopforge.cli import main
from loopforge.experiment import aggregate, format_report, run_experiment
from loopforge.search import SearchConfig

TINY = SearchConfig(budget=6, sizes=(8, 14), per_size=2)


def test_experiment_runs_every_strategy_and_seed(tmp_path):
    messages = []
    run_experiment(tmp_path, ["random", "evolve"], [0, 1], TINY, progress=messages.append)
    for strategy in ("random", "evolve"):
        for seed in (0, 1):
            assert (tmp_path / f"{strategy}-s{seed}" / "summary.json").exists()
    assert len(messages) == 4
    exp = json.loads((tmp_path / "experiment.json").read_text())
    assert exp["references"]["two_opt"]["dev"] == pytest.approx(1.0)
    assert exp["references"]["nearest_neighbor"]["dev"] > 1.0


def test_report_contains_strategies_and_references(tmp_path):
    run_experiment(tmp_path, ["random", "hill_climb"], [0, 1], TINY)
    report = format_report(aggregate(tmp_path))
    assert "| random | 2 |" in report and "| hill_climb | 2 |" in report
    assert "two_opt" in report and "nearest_neighbor" in report
    assert "held-out" in report.lower()


def test_report_handles_a_single_run_without_a_standard_deviation(tmp_path):
    run_experiment(tmp_path, ["evolve"], [0], TINY)
    report = format_report(aggregate(tmp_path))
    assert "±" not in report.split("Mean best-so-far")[0].split("|---|")[-1]


def test_runs_in_an_experiment_are_independent_and_reproducible(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    run_experiment(a, ["evolve"], [2], TINY)
    run_experiment(b, ["evolve"], [2], TINY)
    pa = (a / "evolve-s2" / "programs.jsonl").read_text()
    pb = (b / "evolve-s2" / "programs.jsonl").read_text()
    strip = lambda text: [json.loads(l)["source"] for l in text.splitlines()]  # noqa: E731
    assert strip(pa) == strip(pb)


# ---------- CLI ----------

SMALL = ["--sizes", "8,14", "--per-size", "2"]


def test_cli_search_and_report(tmp_path, capsys):
    assert main(["search", "--budget", "5", "--seed", "1", "--out", str(tmp_path), *SMALL]) == 0
    out = capsys.readouterr().out
    assert "held-out test" in out
    run_dir = tmp_path / "mutation-evolve-s1"
    assert (run_dir / "best.py").exists()
    assert main(["report", str(run_dir)]) == 0
    assert "iter    0" in capsys.readouterr().out


def test_cli_search_never_overwrites_an_old_run(tmp_path):
    for _ in range(2):
        main(["search", "--budget", "2", "--out", str(tmp_path), *SMALL])
    assert (tmp_path / "mutation-evolve-s0").exists() and (tmp_path / "mutation-evolve-s0-2").exists()


def test_cli_experiment_writes_a_report(tmp_path, capsys):
    out = tmp_path / "exp"
    assert main(["experiment", "--budget", "4", "--seeds", "2", "--strategies", "random,evolve",
                 "--out", str(out), *SMALL]) == 0
    assert (out / "report.md").exists()
    assert "| evolve | 2 |" in capsys.readouterr().out


def test_cli_best_program_can_be_evaluated_again(tmp_path, capsys):
    main(["search", "--budget", "3", "--out", str(tmp_path), *SMALL])
    capsys.readouterr()
    assert main(["eval", str(tmp_path / "mutation-evolve-s0" / "best.py")]) == 0
