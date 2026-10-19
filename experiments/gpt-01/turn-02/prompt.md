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

## Current program (score 0.9772; by size: n=25: 0.996, n=50: 0.967, n=100: 0.969)
```python
import math
import random


def solve(points):
    n = len(points)
    if n <= 2:
        return list(range(n))

    px = [p[0] for p in points]
    py = [p[1] for p in points]

    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i):
            d = math.hypot(px[i] - px[j], py[i] - py[j])
            dist[i][j] = dist[j][i] = d

    if n <= 35:
        k = n - 1
    else:
        k = min(24, n - 1)

    near = []
    for i in range(n):
        near.append(sorted(
            (j for j in range(n) if j != i),
            key=lambda j: (dist[i][j], j)
        )[:k])

    def length(tour):
        return sum(dist[tour[i]][tour[(i + 1) % n]]
                   for i in range(n))

    def two_opt(tour, candidate_only=False, max_passes=40):
        tour = tour[:]
        pos = [0] * n
        for i, v in enumerate(tour):
            pos[v] = i

        for _ in range(max_passes):
            improved = False
            for i in range(n):
                a = tour[i]
                b = tour[(i + 1) % n]
                dab = dist[a][b]

                candidates = near[a] if candidate_only else range(n)
                for c in candidates:
                    j = pos[c]
                    if j == i or j == (i + 1) % n:
                        continue

                    if (j + 1) % n == i:
                        continue

                    if j < i:
                        if i == n - 1:
                            continue
                        continue

                    d = tour[(j + 1) % n]
                    if d == a:
                        continue

                    delta = dist[a][c] + dist[b][d] - dab - dist[c][d]
                    if delta < -1e-12:
                        l = i + 1
                        r = j
                        tour[l:r + 1] = reversed(tour[l:r + 1])
                        for q in range(l, r + 1):
                            pos[tour[q]] = q
                        improved = True
                        break

                if improved:
                    break

            if not improved:
                break

        return tour

    def relocate(tour, max_passes=3):
        tour = tour[:]
        for _ in range(max_passes):
            improved = False
            for i in range(n):
                v = tour[i]
                a = tour[(i - 1) % n]
                b = tour[(i + 1) % n]

                candidates = near[v]
                for c in candidates:
                    j = -1
                    # Candidate c is the successor of the insertion edge.
                    # Locate its predecessor in the current cyclic tour.
                    for q in range(n):
                        if tour[q] == c:
                            j = q
                            break
                    if j < 0 or j == i or j == (i + 1) % n:
                        continue

                    u = tour[(j - 1) % n]
                    w = tour[j]

                    delta = (
                        dist[a][b] + dist[u][v] + dist[v][w]
                        - dist[a][v] - dist[v][b] - dist[u][w]
                    )
                    if delta < -1e-12:
                        tour.pop(i)
                        if i < j:
                            j -= 1
                        tour.insert(j, v)
                        improved = True
                        break
                if improved:
                    break
            if not improved:
                break
        return tour

    def nearest_neighbor(start):
        unused = [True] * n
        unused[start] = False
        tour = [start]
        current = start

        for _ in range(n - 1):
            best = -1
            best_d = float("inf")
            for j in near[current]:
                if unused[j] and dist[current][j] < best_d:
                    best = j
                    best_d = dist[current][j]

            if best < 0:
                best = min(
                    (j for j in range(n) if unused[j]),
                    key=lambda j: (dist[current][j], j)
                )

            tour.append(best)
            unused[best] = False
            current = best

        return tour

    starts = list(range(n))
    starts.sort(key=lambda i: (
        (px[i] - 0.5) ** 2 + (py[i] - 0.5) ** 2, i
    ))

    if n <= 35:
        chosen_starts = list(range(n))
    else:
        chosen_starts = []
        for q in range(12):
            chosen_starts.append(starts[q * (n - 1) // 11])
        chosen_starts.extend([0, n // 4, n // 2, 3 * n // 4])
        chosen_starts = list(dict.fromkeys(chosen_starts))

    best_tour = list(range(n))
    best_len = float("inf")

    for start in chosen_starts:
        tour = nearest_neighbor(start)
        tour = two_opt(tour, candidate_only=False, max_passes=20)
        tour = two_opt(tour, candidate_only=True, max_passes=30)
        tour = relocate(tour, max_passes=2)
        tour = two_opt(tour, candidate_only=True, max_passes=20)

        value = length(tour)
        if value < best_len:
            best_len = value
            best_tour = tour

    # Improve a deterministic geometric seed as an additional starting point.
    geometric = sorted(range(n), key=lambda i: (
        math.atan2(py[i] - 0.5, px[i] - 0.5), i
    ))
    geometric = two_opt(geometric, candidate_only=False, max_passes=40)
    geometric = two_opt(geometric, candidate_only=True, max_passes=40)
    geometric = relocate(geometric, max_passes=3)
    geometric = two_opt(geometric, candidate_only=True, max_passes=30)

    value = length(geometric)
    if value < best_len:
        best_tour = geometric

    return [int(i) for i in best_tour]

```
## Other programs found so far (for inspiration)
Program with score 1.1524; by size: n=25: 1.110, n=50: 1.161, n=100: 1.187:
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
