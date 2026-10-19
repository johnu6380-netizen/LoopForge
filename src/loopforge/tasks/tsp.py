"""The Euclidean Traveling Salesman Problem (TSP) task.

A *candidate* is Python source code that defines::

    def solve(points: list[tuple[float, float]]) -> list[int]

``points`` are cities in the unit square. The function must return a tour: a
list containing every city index 0..n-1 exactly once. The tour is closed (the
salesman returns to the start), and shorter is better.

This module is deliberately strict about what counts as a valid tour, because
the whole system depends on the evaluator being impossible to cheat.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

Point = tuple[float, float]

# Instance sizes used for scoring. Mixed sizes stop a candidate from overfitting
# to one n.
DEFAULT_SIZES = (25, 50, 100)
DEFAULT_PER_SIZE = 4

# Dev and test sets use different seed ranges. The search loop only ever sees
# the dev set; the test set is for the final, honest numbers in the write-up.
DEV_BASE_SEED = 1_000
TEST_BASE_SEED = 2_000_000


class InvalidTour(ValueError):
    """Raised when a candidate returns something that is not a valid tour."""


def generate_instance(n: int, seed: int) -> list[Point]:
    """Return ``n`` uniformly random cities in the unit square (deterministic)."""
    if n < 1:
        raise ValueError("n must be at least 1")
    rng = random.Random(seed)
    return [(rng.random(), rng.random()) for _ in range(n)]


@dataclass(frozen=True)
class InstanceSet:
    """A named, reproducible collection of TSP instances."""

    name: str
    instances: tuple[tuple[Point, ...], ...]

    def __len__(self) -> int:
        return len(self.instances)


def make_instance_set(
    name: str,
    base_seed: int,
    sizes: tuple[int, ...] = DEFAULT_SIZES,
    per_size: int = DEFAULT_PER_SIZE,
) -> InstanceSet:
    """Build a deterministic set: ``per_size`` instances for each size."""
    instances = []
    for size in sizes:
        for k in range(per_size):
            seed = base_seed + size * 1_000 + k
            instances.append(tuple(generate_instance(size, seed)))
    return InstanceSet(name=name, instances=tuple(instances))


def dev_set() -> InstanceSet:
    return make_instance_set("dev", DEV_BASE_SEED)


def test_set() -> InstanceSet:
    return make_instance_set("test", TEST_BASE_SEED)


def validate_tour(tour: object, n: int) -> list[int]:
    """Check that ``tour`` is a permutation of range(n); return it as a list.

    Rejects: non-sequences, wrong length, non-int entries (bools and floats
    included), out-of-range indices, and duplicates.
    """
    if not isinstance(tour, (list, tuple)):
        raise InvalidTour(f"tour must be a list or tuple, got {type(tour).__name__}")
    if len(tour) != n:
        raise InvalidTour(f"tour has {len(tour)} cities, expected {n}")
    seen: set[int] = set()
    for city in tour:
        # bool is a subclass of int; True/False must not sneak in as 1/0.
        if type(city) is not int:
            raise InvalidTour(f"tour entries must be int, got {type(city).__name__}")
        if city < 0 or city >= n:
            raise InvalidTour(f"city index {city} out of range 0..{n - 1}")
        if city in seen:
            raise InvalidTour(f"city {city} appears more than once")
        seen.add(city)
    return list(tour)


def tour_length(points: list[Point] | tuple[Point, ...], tour: list[int]) -> float:
    """Length of the closed tour."""
    n = len(tour)
    if n < 2:
        return 0.0
    total = 0.0
    for i in range(n):
        total += math.dist(points[tour[i]], points[tour[(i + 1) % n]])
    return total
