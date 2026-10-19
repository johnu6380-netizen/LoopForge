import math

import pytest

from loopforge.evaluator import CandidateError, compile_candidate, evaluate
from loopforge.seeds import load_tsp_seed_source, tsp_seed_names
from loopforge.tasks.tsp import make_instance_set

# Small set so the test suite stays fast.
SMALL = make_instance_set("small", base_seed=42, sizes=(10, 25), per_size=2)


def fitness_of(name):
    return evaluate(load_tsp_seed_source(name), SMALL)


def test_all_seeds_are_valid():
    for name in tsp_seed_names():
        assert fitness_of(name).valid, name


def test_two_opt_defines_the_reference():
    # The reference *is* 2-opt, so it must score exactly 1.0.
    assert fitness_of("two_opt").fitness == pytest.approx(1.0)


def test_baseline_ordering():
    random_order = fitness_of("random_order").fitness
    nearest = fitness_of("nearest_neighbor").fitness
    two_opt = fitness_of("two_opt").fitness
    assert two_opt <= nearest < random_order


def test_syntax_error_is_invalid_not_a_crash():
    result = evaluate("def solve(points) return []", SMALL)
    assert not result.valid and math.isinf(result.fitness)
    assert "SyntaxError" in result.error


def test_missing_solve_is_invalid():
    result = evaluate("x = 1", SMALL)
    assert not result.valid
    assert "solve" in result.error


def test_runtime_exception_is_invalid():
    result = evaluate("def solve(points):\n    raise RuntimeError('boom')", SMALL)
    assert not result.valid
    assert "boom" in result.error


def test_duplicate_city_is_invalid():
    result = evaluate("def solve(points):\n    return [0] * len(points)", SMALL)
    assert not result.valid
    assert "more than once" in result.error


def test_wrong_length_is_invalid():
    result = evaluate("def solve(points):\n    return list(range(len(points) - 1))", SMALL)
    assert not result.valid


def test_one_bad_instance_invalidates_everything():
    # Correct on small instances, wrong on the 25-city ones: no partial credit.
    src = (
        "def solve(points):\n"
        "    n = len(points)\n"
        "    return list(range(n)) if n < 20 else [0] * n\n"
    )
    result = evaluate(src, SMALL)
    assert not result.valid and math.isinf(result.fitness)
    assert any(i.valid for i in result.instances)


def test_candidate_cannot_corrupt_the_instance():
    before = SMALL.instances
    evaluate("def solve(points):\n    points.clear()\n    return []", SMALL)
    assert SMALL.instances == before


def test_compile_candidate_returns_callable():
    assert callable(compile_candidate("def solve(points):\n    return list(range(len(points)))"))


def test_compile_candidate_raises_on_garbage():
    with pytest.raises(CandidateError):
        compile_candidate("this is not python")


def test_result_to_dict_is_json_safe():
    import json

    bad = evaluate("x = 1", SMALL).to_dict()
    json.dumps(bad)  # would raise on inf
    assert bad["fitness"] is None
