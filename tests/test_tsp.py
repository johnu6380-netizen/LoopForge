import math

import pytest

from loopforge.tasks.tsp import (
    InvalidTour,
    dev_set,
    generate_instance,
    test_set as make_test_set,
    tour_length,
    validate_tour,
)


def test_generate_instance_is_deterministic():
    assert generate_instance(30, seed=7) == generate_instance(30, seed=7)


def test_generate_instance_differs_by_seed():
    assert generate_instance(30, seed=7) != generate_instance(30, seed=8)


def test_points_are_in_unit_square():
    for x, y in generate_instance(200, seed=1):
        assert 0.0 <= x < 1.0 and 0.0 <= y < 1.0


def test_dev_and_test_sets_do_not_overlap():
    dev = set(dev_set().instances)
    test = set(make_test_set().instances)
    assert dev.isdisjoint(test)


def test_instance_sets_are_reproducible():
    assert dev_set().instances == dev_set().instances


def test_validate_accepts_permutation():
    assert validate_tour([2, 0, 1], 3) == [2, 0, 1]
    assert validate_tour((1, 0), 2) == [1, 0]


@pytest.mark.parametrize(
    "bad",
    [
        [0, 1],  # too short
        [0, 1, 2, 3],  # too long
        [0, 1, 1],  # duplicate
        [0, 1, 3],  # out of range
        [0, 1, -1],  # negative
        [0.0, 1.0, 2.0],  # floats
        [True, 1, 2],  # bool is not an int here
        "012",  # not a list
        None,
        {0, 1, 2},  # a set, unordered
    ],
)
def test_validate_rejects_bad_tours(bad):
    with pytest.raises(InvalidTour):
        validate_tour(bad, 3)


def test_tour_length_square():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert tour_length(square, [0, 1, 2, 3]) == pytest.approx(4.0)
    # crossing tour is longer
    assert tour_length(square, [0, 2, 1, 3]) == pytest.approx(2 + 2 * math.sqrt(2))


def test_tour_length_is_rotation_and_reversal_invariant():
    pts = generate_instance(20, seed=3)
    tour = list(range(20))
    base = tour_length(pts, tour)
    assert tour_length(pts, tour[5:] + tour[:5]) == pytest.approx(base)
    assert tour_length(pts, tour[::-1]) == pytest.approx(base)
