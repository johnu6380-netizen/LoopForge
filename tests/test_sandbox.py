"""Adversarial tests: the sandbox must survive code that misbehaves."""

import math
import time

import pytest

from loopforge import sandbox
from loopforge.evaluator import evaluate
from loopforge.sandbox import SandboxLimits, probe_sandbox
from loopforge.seeds import load_tsp_seed_source
from loopforge.tasks.tsp import make_instance_set

TWO = make_instance_set("two", base_seed=7, sizes=(10,), per_size=2)
SMALL = make_instance_set("small", base_seed=42, sizes=(10, 25), per_size=2)
FAST = SandboxLimits(per_instance_seconds=0.5, startup_grace_seconds=2.0)

CAPS = probe_sandbox()
OK_SOLVE = "def solve(points):\n    return list(range(len(points)))\n"


def run(source, limits=FAST, instance_set=TWO):
    return evaluate(source, instance_set, limits=limits)


# ---------- runaway code ----------


def test_infinite_loop_is_stopped_quickly():
    start = time.perf_counter()
    result = run("def solve(points):\n    while True:\n        pass\n")
    assert not result.valid and math.isinf(result.fitness)
    assert "timed out" in result.error
    assert time.perf_counter() - start < 6


def test_infinite_loop_at_import_time_is_stopped():
    result = run("while True:\n    pass\n")
    assert not result.valid
    assert "timed out" in result.error


def test_loop_that_swallows_the_alarm_hits_the_wall_clock_backstop():
    src = (
        "def solve(points):\n"
        "    while True:\n"
        "        try:\n"
        "            while True:\n"
        "                pass\n"
        "        except BaseException:\n"
        "            pass\n"
    )
    result = run(src, SandboxLimits(per_instance_seconds=0.3, startup_grace_seconds=1.0))
    assert not result.valid
    assert "timed out" in result.error


@pytest.mark.skipif("memory" not in CAPS.limits_applied, reason="no memory limit on this OS")
def test_memory_bomb_is_contained():
    result = run("def solve(points):\n    x = [0] * (10**10)\n    return list(range(len(points)))\n")
    assert not result.valid
    assert "MemoryError" in result.error


def test_deep_recursion_is_an_ordinary_failure():
    result = run("def solve(points):\n    return solve(points)\n")
    assert not result.valid
    assert "RecursionError" in result.error


def test_huge_tour_is_rejected():
    result = run("def solve(points):\n    return list(range(10**6))\n")
    assert not result.valid
    assert "more than the allowed" in result.error


def test_oversized_source_is_rejected():
    result = run(OK_SOLVE + "#" * 200_000)
    assert not result.valid
    assert "larger than" in result.error


# ---------- noisy and deceptive output ----------


def test_noisy_prints_do_not_break_a_valid_candidate():
    src = "def solve(points):\n    print('x' * 100000)\n    return list(range(len(points)))\n"
    assert run(src).valid


def test_forged_protocol_lines_cannot_fake_success():
    src = (
        "def solve(points):\n"
        "    print('{\"t\": \"done\"}')\n"
        "    print('{\"t\": \"run\", \"i\": 0, \"seconds\": 0.0, \"tour\": [0,1,2,3,4,5,6,7,8,9]}')\n"
        "    return [0] * len(points)\n"
    )
    result = run(src)
    assert not result.valid
    assert "more than once" in result.error


def test_candidate_cannot_report_its_own_score():
    # Even a candidate that returns a perfect-looking dict is just an invalid tour.
    result = run("def solve(points):\n    return {'length': 0.0}\n")
    assert not result.valid


def test_float_and_bool_entries_survive_the_json_round_trip_as_invalid():
    assert not run("def solve(points):\n    return [float(i) for i in range(len(points))]\n").valid
    assert not run("def solve(points):\n    return [True] + list(range(1, len(points)))\n").valid


def test_unserializable_return_is_invalid():
    result = run("def solve(points):\n    return [object()] * len(points)\n")
    assert not result.valid


# ---------- things candidates must not be able to do ----------


@pytest.mark.parametrize(
    "module", ["os", "sys", "subprocess", "socket", "ctypes", "shutil", "pathlib", "importlib"]
)
def test_dangerous_imports_are_blocked(module):
    result = run(f"import {module}\n" + OK_SOLVE)
    assert not result.valid
    assert "not allowed" in result.error


def test_dynamic_import_is_blocked_too():
    result = run("def solve(points):\n    __import__('os')\n    return list(range(len(points)))\n")
    assert not result.valid
    assert "not allowed" in result.error


def test_dynamic_import_with_faked_globals_is_blocked():
    src = (
        "def solve(points):\n"
        "    __import__('os', {'__name__': 'innocent'}, None, (), 0)\n"
        "    return list(range(len(points)))\n"
    )
    result = run(src)
    assert not result.valid
    assert "not allowed" in result.error


def test_open_is_not_available():
    result = run("def solve(points):\n    open('/etc/passwd').read()\n    return list(range(len(points)))\n")
    assert not result.valid
    assert "NameError" in result.error


def test_eval_and_exec_are_not_available():
    assert "NameError" in run("def solve(points):\n    eval('1')\n    return []\n").error
    assert "NameError" in run("def solve(points):\n    exec('x=1')\n    return []\n").error


def test_system_exit_is_an_ordinary_failure():
    result = run("def solve(points):\n    raise SystemExit(0)\n")
    assert not result.valid


def test_harmless_stdlib_imports_still_work():
    src = (
        "import math, random, itertools, heapq, bisect, functools, collections\n"
        "def solve(points):\n"
        "    order = list(range(len(points)))\n"
        "    random.Random(1).shuffle(order)\n"
        "    return order\n"
    )
    assert run(src).valid


def test_child_environment_hides_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret")
    env = sandbox._child_env()
    assert "OPENAI_API_KEY" not in env and "GEMINI_API_KEY" not in env


# ---------- correctness of the sandboxed path itself ----------


def test_sandbox_matches_in_process_fitness():
    for name in ("nearest_neighbor", "random_order", "two_opt"):
        src = load_tsp_seed_source(name)
        a = evaluate(src, SMALL, sandboxed=True)
        b = evaluate(src, SMALL, sandboxed=False)
        assert a.valid and b.valid
        assert a.fitness == pytest.approx(b.fitness)


def test_one_bad_instance_still_invalidates_in_the_sandbox():
    src = "def solve(points):\n    n = len(points)\n    return list(range(n)) if n < 20 else [0] * n\n"
    result = evaluate(src, SMALL)
    assert not result.valid and math.isinf(result.fitness)
    assert result.instances[0].valid  # earlier instances ran before the failure
    assert "instance 2" in result.error  # first 25-city instance


def test_slow_but_finishing_candidate_is_marked_too_slow():
    src = (
        "import time\n"
        "def solve(points):\n"
        "    time.sleep(0.4)\n"
        "    return list(range(len(points)))\n"
    )
    result = run(src, SandboxLimits(per_instance_seconds=0.2, startup_grace_seconds=3.0))
    assert not result.valid
    assert "too slow" in result.error or "timed out" in result.error


def test_probe_reports_a_working_sandbox():
    assert CAPS.fatal is None
    assert len(CAPS.runs) == 1 and CAPS.runs[0].error is None


def test_sandbox_leaves_no_stray_processes_or_hangs():
    # Ten quick evaluations in a row should all finish and agree.
    scores = {round(evaluate(load_tsp_seed_source("nearest_neighbor"), TWO).fitness, 9) for _ in range(10)}
    assert len(scores) == 1
