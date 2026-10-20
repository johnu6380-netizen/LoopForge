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
                                    else:
                                        # v precedes c: v, s1..s0, c
                                        order = segn[::-1]
                                        t[:] = rest[:k] + order + rest[k:]
                                    for ii, cc in enumerate(t):
                                        pos[cc] = ii
                                    push(p); push(q); push(c); push(v)
                                    push(s0); push(s1)
                                    done = True
                                    break
                            if done:
                                break
                        if done:
                            improved_any = True
                            break
                    if improved_any:
                        break
        return t

    tour = or_opt(tour)
    best = tour[:]
    best_len = length(best)
    cur = best[:]
    cur_len = best_len
    rng = random.Random(0)

    if n >= 8:
        while time.time() - t0 < budget:
            # localized double-bridge with small segments
            st = rng.randrange(0, n)
            rot = cur[st:] + cur[:st]
            m = min(n - 1, 50)
            a, b, c = sorted(rng.sample(range(1, m + 1), 3))
            cand = rot[:a] + rot[b:c] + rot[a:b] + rot[c:]
            touched = [cand[0], cand[a - 1 if a > 0 else 0]]
            touched = set()
            for idx in (0, a - 1, a, b - 1, b, c - 1, c):
                if 0 <= idx < n:
                    touched.add(cand[idx])
            # nodes at the new junctions
            junction = []
            L1 = a
            L2 = c - b
            L3 = b - a
            for idx in (L1 - 1, L1, L1 + L2 - 1, L1 + L2, L1 + L2 + L3 - 1, L1 + L2 + L3):
                if 0 <= idx < n:
                    junction.append(cand[idx])
            cand = or_opt(cand, junction)
            cl = length(cand)
            if cl < cur_len - 1e-12:
                cur, cur_len = cand, cl
                if cl < best_len:
                    best, best_len = cand[:], cl

    return [int(x) for x in best]
