import random


def solve(points):
    """Worst-case baseline: visit cities in a random (but fixed-seed) order."""
    order = list(range(len(points)))
    random.Random(0).shuffle(order)
    return order
