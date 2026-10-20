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
    budget = 5.0

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

    def local_search(t):
        # 2-opt + or-opt, neighbor lists, first improvement, rebuild positions
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
                da = d[a]
                for c in neigh[a]:
                    dac = da[c]
                    if dac >= dab:
                        break
                    j = pos[c]
                    e = t[(j + 1) % n]
                    if c == b or e == a:
                        continue
                    if dac + d[b][e] - dab - d[c][e] < -1e-10:
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
                            i1 += 1
                            if i1 == n:
                                i1 = 0
                            j1 -= 1
                            if j1 < 0:
                                j1 = n - 1
                        improved = True
                        break
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
                                        pos[cc] = ii
                                    improved = True
                                    done = True
                                    break
                            if done:
                                break
                        if done:
                            break
        return t

    tour = local_search(tour)
    best = tour[:]
    best_len = length(best)
    cur = best[:]
    cur_len = best_len
    rng = random.Random(0)

    if n >= 8:
        while time.time() - t0 < budget:
            m = min(n - 1, 50)
            st = rng.randrange(0, n)
            rot = cur[st:] + cur[:st]
            a, b, c = sorted(rng.sample(range(1, m + 1), 3))
            cand = rot[:a] + rot[b:c] + rot[a:b] + rot[c:]
            cand = local_search(cand)
            cl = length(cand)
            if cl < cur_len - 1e-12:
                cur, cur_len = cand, cl
                if cl < best_len:
                    best, best_len = cand[:], cl

    return [int(x) for x in best]
```