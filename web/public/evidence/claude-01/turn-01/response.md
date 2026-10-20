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