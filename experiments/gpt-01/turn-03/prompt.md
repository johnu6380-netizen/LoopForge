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
Program with score 0.9786; by size: n=25: 0.996, n=50: 0.972, n=100: 0.968:
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

    def tour_length(t):
        return sum(dist[t[i]][t[(i + 1) % n]] for i in range(n))

    # Geometric candidate lists, augmented with angularly diverse neighbors.
    k = min(n - 1, 20 if n >= 60 else 28)
    near = []
    near_sets = []
    for i in range(n):
        order = sorted(
            (j for j in range(n) if j != i),
            key=lambda j: (dist[i][j], j)
        )
        near.append(order[:k])
        near_sets.append(set(order[:k]))

    def make_pos(t):
        pos = [0] * n
        for i, v in enumerate(t):
            pos[v] = i
        return pos

    def two_opt(tour, candidate=True, max_passes=50):
        t = tour[:]
        pos = make_pos(t)
        for _ in range(max_passes):
            changed = False
            for i in range(n):
                a = t[i]
                b = t[(i + 1) % n]
                if candidate:
                    cs = near[a]
                else:
                    cs = range(n)
                for c in cs:
                    j = pos[c]
                    if j <= i + 1 or (i == 0 and j == n - 1):
                        continue
                    d = t[(j + 1) % n]
                    if dist[a][c] + dist[b][d] >= (
                        dist[a][b] + dist[c][d] - 1e-12
                    ):
                        continue
                    t[i + 1:j + 1] = reversed(t[i + 1:j + 1])
                    for q in range(i + 1, j + 1):
                        pos[t[q]] = q
                    changed = True
                    break
                if changed:
                    break
            if not changed:
                break
        return t

    def relocate(tour, max_passes=3, block_sizes=(1,)):
        t = tour[:]
        for _ in range(max_passes):
            pos = make_pos(t)
            changed = False
            for size in block_sizes:
                if size >= n - 2:
                    continue
                for i in range(n):
                    if i + size >= n:
                        continue
                    block = t[i:i + size]
                    if not block:
                        continue
                    a = t[(i - 1) % n]
                    z = t[i + size - 1]
                    b = t[(i + size) % n]
                    removed = dist[a][b]
                    removed -= dist[a][block[0]] + dist[z][b]
                    if size > 1:
                        for q in range(size - 1):
                            removed += dist[block[q]][block[q + 1]]
                    for v in block:
                        for c in near[v]:
                            j = pos[c]
                            if i <= j < i + size:
                                continue
                            u = t[(j - 1) % n]
                            w = t[j]
                            # Insert the block before c, after removal.
                            delta = (
                                dist[a][b]
                                + dist[u][block[0]]
                                + dist[block[-1]][w]
                                - dist[a][block[0]]
                                - dist[block[-1]][b]
                                - dist[u][w]
                            )
                            if size > 1:
                                delta += sum(
                                    dist[block[q]][block[q + 1]]
                                    for q in range(size - 1)
                                )
                            if delta >= -1e-12:
                                continue
                            old = t[:]
                            del t[i:i + size]
                            jj = t.index(c)
                            t[jj:jj] = block
                            changed = True
                            break
                        if changed:
                            break
                    if changed:
                        break
                if changed:
                    break
            if not changed:
                break
        return t

    def nearest_neighbor(start):
        unused = [True] * n
        unused[start] = False
        t = [start]
        cur = start
        for _ in range(n - 1):
            best = -1
            bestd = float("inf")
            for j in near[cur]:
                if unused[j] and dist[cur][j] < bestd:
                    best = j
                    bestd = dist[cur][j]
            if best < 0:
                for j in range(n):
                    if unused[j] and dist[cur][j] < bestd:
                        best = j
                        bestd = dist[cur][j]
            t.append(best)
            unused[best] = False
            cur = best
        return t

    def insertion_seed(start):
        # Farthest-point expansion with cheapest insertion.
        chosen = [start]
        used = [False] * n
        used[start] = True
        second = max(
            (j for j in range(n) if j != start),
            key=lambda j: (dist[start][j], -j)
        )
        chosen.append(second)
        used[second] = True
        while len(chosen) < n:
            v = max(
                (j for j in range(n) if not used[j]),
                key=lambda j: (
                    min(dist[j][u] for u in chosen), -j
                )
            )
            best_delta = float("inf")
            best_i = 0
            m = len(chosen)
            for i in range(m):
                a = chosen[i]
                b = chosen[(i + 1) % m]
                delta = dist[a][v] + dist[v][b] - dist[a][b]
                if delta < best_delta:
              
# ... (truncated)
```
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
