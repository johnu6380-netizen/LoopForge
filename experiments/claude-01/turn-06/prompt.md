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
    budget = 6.0 if n > 12 else 0.5

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

    def or_opt(t, queue_nodes=None):
        """Or-opt local search: 2-opt + Or-opt using neighbor lists and a work queue."""
        pos = [0] * n
        for i, c in enumerate(t):
            pos[c] = i
        if queue_nodes is None:
            queue = list(range(n))
        else:
            queue = list(queue_nodes)
        inq = [False] * n
        for c in queue:
            inq[c] = True

        def reverse(i1, j1):
            # reverse cyclic path from position i1 to j1
            L = (j1 - i1) % n + 1
            if L * 2 > n:
                i1, j1 = (j1 + 1) % n, (i1 - 1) % n
                L = n - L
            for _ in range(L // 2):
                x = t[i1]
                y = t[j1]
                t[i1] = y
                t[j1] = x
                pos[y] = i1
                pos[x] = j1
                i1 += 1
                if i1 == n:
                    i1 = 0
                j1 -= 1
                if j1 < 0:
                    j1 = n - 1

        def push(c):
            if not inq[c]:
                inq[c] = True
                queue.append(c)

        while queue:
            a = queue.pop()
            inq[a] = False
            improved_any = True
            while improved_any:
                improved_any = False
                i = pos[a]
                # successor direction
                b = t[(i + 1) % n]
                dab = d[a][b]
                da = d[a]
                for c in neigh[a]:
                    dac = da[c]
                    if dac >= dab:
                        break
                    j = pos[c]
                    e = t[(j + 1) % n]
                    if c == b or e == a:
                        continue
                    delta = dac + d[b][e] - dab - d[c][e]
                    if delta < -1e-10:
                        reverse((i + 1) % n, j)
                        push(a); push(b); push(c); push(e)
                        improved_any = True
                        break
                if improved_any:
                    continue
                # predecessor direction
                pa = t[(i - 1) % n]
                dpa = d[pa][a]
                for c in neigh[a]:
                    dac = da[c]
                    if dac >= dpa:
                        break
                    j = pos[c]
                    pc = t[(j - 1) % n]
                    if c == pa or pc == a:
                        continue
                    delta = dac + d[pa][pc] - dpa - d[pc][c]
                    if delta < -1e-10:
                        reverse(i, (j - 1) % n)
                        push(a); push(pa); push(c); push(pc)
                        improved_any = True
                        break
                if improved_any:
                    continue
                # or-opt: move segment starting at a, lengths 1..3, either direction
                for seg in (1, 2, 3):
                    if seg >= n - 3:
                        break
                    for direction in (0, 1):
                        i = pos[a]
                        if direction == 0:
                            idxs = [(i + k) % n for k in range(seg)]
                        else:
                            idxs = [(i - k) % n for k in range(seg)]
                        segn = [t[x] for x in idxs]
                        s0 = segn[0]
                        s1 = segn[-1]
                        if direction == 0:
                            p = t[(i - 1) % n]
                            q = t[(i + seg) % n]
                        else:
                            p = t[(i + 1) % n]
                            q = t[(i - seg) % n]
                        rg = d[p][s0] + d[s1][q] - d[p][q]
                        if rg <= 1e-10:
                            continue
                        segset = set(segn)
                        done = False
                        for c in neigh[s0]:
                            dsc = d[s0][c]
                            if dsc >= rg:
                                break
                            if c in segset:
                                continue
                            j = pos[c]
                            for v in (t[(j + 1) % n], t[(j - 1) % n]):
                                if v in segset:
                                    continue
                                # insert segment between c and v with s0 adjacent to c
                                add = dsc + d[s1][v] - d[c][v]
                                if add - rg < -1e-10:
                                    # build new tour
                                    # orientation: c, s0..s1, v
                                    rest = [x for x in t if x not in segset]
                                    # position of c in rest
                                    k = rest.index(c)
                                    nxt = rest[(k + 1) % len(rest)]
                                    if nxt == v:
                                        order = segn
                                        t[:] = rest[:k + 1] + order + rest[k + 1:]
                            
# ... (truncated)
```
## Other programs found so far (for inspiration)
Program with score 0.9706; by size: n=25: 0.996, n=50: 0.964, n=100: 0.952:
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
Program with score 0.9710; by size: n=25: 0.996, n=50: 0.964, n=100: 0.953:
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
    budget = 5.0 if n > 12 else 1.0

    d = [[0.0] * n for _ in range(n)]
    for i in range(n):
        xi, yi = points[i]
        row = d[i]
        for j in range(n):
            row[j] = math.hypot(xi - points[j][0], yi - points[j][1])

    K = min(12, n - 1)
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

    def oropt(t):
        """Or-opt local search: 2-opt + or-opt with neighbor lists, array based."""
        pos = [0] * n
        for i, c in enumerate(t):
            pos[c] = i
        improved = True
        while improved:
            improved = False
            for i in range(n):
                a = t[i]
                b = t[(i + 1) % n]
                dab = d[a][b]
                # successor direction 2-opt
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
                        i1 = (i + 1) % n
                        j1 = j
                        L = (j1 - i1) % n + 1
                        if L * 2 > n:
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
                else:
                    # predecessor direction 2-opt
                    a = t[i]
                    pa = t[(i - 1) % n]
                    dpa = d[pa][a]
                    for c in neigh[a]:
                        dac = d[a][c]
                        if dac >= dpa:
                            break
                        j = pos[c]
                        pc = t[(j - 1) % n]
                        if c == pa or pc == a:
                            continue
                        delta = dac + d[pa][pc] - dpa - d[pc][c]
                        if delta < -1e-10:
                            # remove (pa,a),(pc,c); add (a,c),(pa,pc): reverse a..pc
                            i1 = i
                            j1 = (j - 1) % n
                            L = (j1 - i1) % n + 1
                            if L * 2 > n:
                                i1, j1 = j, (i - 1) % n
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
                            for (u, v) in ((c, t[(j + 1) % n]), (t[(j - 1) % n], c)):
                                if u in segset or v in segset:
                                    continue
                                if end == s0:
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
              
# ... (truncated)
```
## Answer format
First line: `DESCRIPTION: <one sentence: what you changed and why>`
Then ONE ```python code block with the COMPLETE new program (not a diff).
