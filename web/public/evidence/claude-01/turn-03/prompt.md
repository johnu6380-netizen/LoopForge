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

## Current program (score 0.9706; by size: n=25: 0.996, n=50: 0.964, n=100: 0.952)
```python
import math
import random
import time


def solve(points):
    n = len(points)
    if n == 0:
        return []
    if n <= 3:
        return list(range(n))

    t0 = time.time()
    budget = 4.0

    d = [[0.0] * n for _ in range(n)]
    for i in range(n):
        xi, yi = points[i]
        row = d[i]
        for j in range(n):
            row[j] = math.hypot(xi - points[j][0], yi - points[j][1])

    K = min(10, n - 1)
    neigh = []
    for i in range(n):
        order = sorted((j for j in range(n) if j != i), key=lambda j: (d[i][j], j))
        neigh.append(order[:K])

    # nearest neighbor construction
    tour = [0]
    unv = set(range(1, n))
    cur = 0
    while unv:
        cur = min(unv, key=lambda j: (d[cur][j], j))
        unv.remove(cur)
        tour.append(cur)

    def length(t):
        return sum(d[t[i]][t[(i + 1) % n]] for i in range(n))

    def two_opt_or(t):
        # 2-opt with neighbor lists + or-opt (segments 1..3), array based
        pos = [0] * n
        for i, c in enumerate(t):
            pos[c] = i
        improved = True
        while improved:
            improved = False
            # 2-opt
            for i in range(n):
                a = t[i]
                b = t[(i + 1) % n]
                dab = d[a][b]
                for c in neigh[a]:
                    dac = d[a][c]
                    if dac >= dab:
                        break
                    j = pos[c]
                    e = t[(j + 1) % n]
                    if c == b or e == a:
                        continue
                    delta = dac + d[b][e] - dab - d[c][e]
                    if delta < -1e-10:
                        # reverse path b..c (cyclic)
                        i1 = (i + 1) % n
                        j1 = j
                        L = (j1 - i1) % n + 1
                        if L * 2 > n:
                            # reverse complement: e..a
                            i1, j1 = (j + 1) % n, i
                            L = n - L
                        for _ in range(L // 2):
                            x = t[i1]
                            y = t[j1]
                            t[i1] = y
                            t[j1] = x
                            pos[y] = i1
                            pos[x] = j1
                            i1 = (i1 + 1) % n
                            j1 = (j1 - 1) % n
                        improved = True
                        break
            # or-opt
            for seg in (1, 2, 3):
                if seg >= n - 3:
                    break
                for i in range(n):
                    s0 = t[i]
                    s1 = t[(i + seg - 1) % n]
                    p = t[(i - 1) % n]
                    q = t[(i + seg) % n]
                    rg = d[p][s0] + d[s1][q] - d[p][q]
                    if rg <= 1e-10:
                        continue
                    segn = [t[(i + k) % n] for k in range(seg)]
                    segset = set(segn)
                    done = False
                    for end in (s0, s1):
                        for c in neigh[end]:
                            if d[end][c] >= rg:
                                break
                            if c in segset:
                                continue
                            j = pos[c]
                            # insert between c and next, or prev and c
                            for (u, v) in ((c, t[(j + 1) % n]), (t[(j - 1) % n], c)):
                                if u in segset or v in segset:
                                    continue
                                if end is s0 or end == s0:
                                    # s0 adjacent to c
                                    if u == c:
                                        add = d[u][s0] + d[s1][v] - d[u][v]
                                        order = segn
                                    else:
                                        add = d[u][s1] + d[s0][v] - d[u][v]
                                        order = segn[::-1]
                                else:
                                    if u == c:
                                        add = d[u][s1] + d[s0][v] - d[u][v]
                                        order = segn[::-1]
                                    else:
                                        add = d[u][s0] + d[s1][v] - d[u][v]
                                        order = segn
                                if add - rg < -1e-10:
                                    rest = [x for x in t if x not in segset]
                                    k = rest.index(u)
                                    t[:] = rest[:k + 1] + order + rest[k + 1:]
                                    for ii, cc in enumerate(t):
                                        pos[cc] = ii
                                    improved = True
                                    done = True
                                    break
                            if done:
                                break
                        if done:
                            break
        return t

    tour = two_opt_or(tour)
    best = tour[:]
    best_len = length(best)
    cur = best[:]
    cur_len = best_len
    rng = random.Random(0)

    if n >= 8:
        while time.time() - t0 < budget:
            # localized double-bridge: small segments
            m = min(n - 1, 50)
            st = rng.randrange(0, n)
            rot = cur[st:] + cur[:st]
            a, b, c = sorted(rng.sample(range(1, m + 1), 3)) if m >= 3 else (1, 2, 3)
            cand = rot[:a] + rot[b:c] + rot[a:b] + rot[c:]
            cand = two_opt_or(cand)
            cl = length(cand)
            if cl < cur_len - 1e-12:
                cur, cur_len = cand, cl
                if cl < best_len:
                    best, best_len = cand[:], cl

    return [int(x) for x in best]

```
## Other programs found so far (for inspiration)
Program with score 0.9711; by size: n=25: 0.996, n=50: 0.964, n=100: 0.953:
```python
import math
import random
import time


def solve(points):
    n = len(points)
    if n == 0:
        return []
    if n <= 3:
        return list(range(n))

    start_time = time.time()
    budget = 3.0

    d = [[0.0] * n for _ in range(n)]
    for i in range(n):
        xi, yi = points[i]
        row = d[i]
        for j in range(n):
            row[j] = math.hypot(xi - points[j][0], yi - points[j][1])

    # nearest neighbor construction
    tour = [0]
    unv = set(range(1, n))
    cur = 0
    while unv:
        cur = min(unv, key=lambda j: (d[cur][j], j))
        unv.remove(cur)
        tour.append(cur)

    def length(t):
        return sum(d[t[i]][t[(i + 1) % n]] for i in range(n))

    def local_search(t):
        improved = True
        while improved:
            improved = False
            # 2-opt
            for i in range(n - 1):
                a, b = t[i], t[i + 1]
                dab = d[a][b]
                for j in range(i + 2, n):
                    if i == 0 and j == n - 1:
                        continue
                    c, e = t[j], t[(j + 1) % n]
                    delta = d[a][c] + d[b][e] - dab - d[c][e]
                    if delta < -1e-12:
                        t[i + 1:j + 1] = reversed(t[i + 1:j + 1])
                        improved = True
                        a, b = t[i], t[i + 1]
                        dab = d[a][b]
            # Or-opt: move segments of length 1..3
            for seg in (1, 2, 3):
                i = 0
                while i < n:
                    if seg >= n - 2:
                        break
                    # segment t[i..i+seg-1] (cyclic via rotation)
                    idx = [(i + k) % n for k in range(seg)]
                    s0, s1 = t[idx[0]], t[idx[-1]]
                    p = t[(i - 1) % n]
                    q = t[(i + seg) % n]
                    remove_gain = d[p][s0] + d[s1][q] - d[p][q]
                    segset = set(idx)
                    best = -1e-12
                    best_pos = None
                    best_rev = False
                    for j in range(n):
                        if j in segset or (j + 1) % n in segset:
                            continue
                        u, v = t[j], t[(j + 1) % n]
                        add1 = d[u][s0] + d[s1][v] - d[u][v]
                        add2 = d[u][s1] + d[s0][v] - d[u][v]
                        if add1 - remove_gain < best:
                            best = add1 - remove_gain
                            best_pos = j
                            best_rev = False
                        if add2 - remove_gain < best:
                            best = add2 - remove_gain
                            best_pos = j
                            best_rev = True
                    if best_pos is not None:
                        seg_nodes = [t[k] for k in idx]
                        if best_rev:
                            seg_nodes.reverse()
                        u = t[best_pos]
                        rest = [x for k, x in enumerate(t) if k not in segset]
                        pos = rest.index(u)
                        t[:] = rest[:pos + 1] + seg_nodes + rest[pos + 1:]
                        improved = True
                    i += 1
        return t

    tour = local_search(tour)
    best = tour[:]
    best_len = length(best)
    cur = best[:]
    cur_len = best_len
    rng = random.Random(0)

    if n >= 8:
        while time.time() - start_time < budget:
            # double-bridge perturbation
            pts = sorted(rng.sample(range(1, n), 3))
            a, b, c = pts
            cand = cur[:a] + cur[b:c] + cur[a:b] + cur[c:]
            cand = local_search(cand)
            cl = length(cand)
            if cl < cur_len - 1e-12:
                cur, cur_len = cand, cl
                if cl < best_len:
                    best, best_len = cand[:], cl

    return [int(x) for x in best]

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
