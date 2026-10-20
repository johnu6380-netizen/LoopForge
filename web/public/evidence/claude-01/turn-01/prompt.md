Answer directly in the format requested at the end. Do not use any tools, do not run or test code, and do not browse the web.

You are an expert in combinatorial optimization and Python. You improve heuristics for the Euclidean Traveling Salesman Problem. You reply with one complete Python program and nothing else except a one-line description.

## Task
Improve a heuristic for the Euclidean Traveling Salesman Problem.
The program must define `solve(points)`. `points` is a list of (x, y) tuples in the unit square.
Return a list containing every city index 0..n-1 exactly once (a closed tour). Shorter is better.

## Scoring
Score = mean over many instances (n from about 25 to 100) of
(your tour length) / (tour length of a plain 2-opt reference). 1.0 ties 2-opt; lower is better.
A program that returns an invalid tour, raises an exception, or takes more than 10 seconds on an instance is INVALID and scores nothing.

## Rules
- Python standard library only. Imports such as math, random, itertools, heapq are fine;
  os, sys, io, files and network access are blocked.
- Deterministic: the same input must give the same tour (seed any randomness, e.g. random.Random(0)).
- Return plain Python ints. Define everything in one file with a top-level `solve`.

## Current program (score 1.1524; by size: n=25: 1.110, n=50: 1.161, n=100: 1.187)
```python
def solve(points):
    """Greedy baseline: always walk to the closest unvisited city."""
    n = len(points)
    if n == 0:
        return []
    tour = [0]
    unvisited = set(range(1, n))
    current = 0
    while unvisited:
        cx, cy = points[current]
        current = min(unvisited, key=lambda j: ((points[j][0] - cx) ** 2 + (points[j][1] - cy) ** 2, j))
        unvisited.remove(current)
        tour.append(current)
    return tour
```
## Answer format
First line: `DESCRIPTION: <one sentence: what you changed and why>`
Then ONE ```python code block with the COMPLETE new program (not a diff).
