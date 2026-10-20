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
                    best_delta = delta
                    best_i = i + 1
            chosen.insert(best_i, v)
            used[v] = True
        return chosen

    def angular_seed(cx, cy):
        return sorted(
            range(n),
            key=lambda i: (
                math.atan2(py[i] - cy, px[i] - cx),
                (px[i] - cx) ** 2 + (py[i] - cy) ** 2,
                i
            )
        )

    def improve(t, full_passes=8, candidate_passes=35):
        t = two_opt(t, False, full_passes)
        t = two_opt(t, True, candidate_passes)
        t = relocate(t, 3, (1, 2))
        t = two_opt(t, True, 25)
        return t

    # Deterministic, spatially diverse starting points.
    center_order = sorted(
        range(n),
        key=lambda i: (
            (px[i] - 0.5) ** 2 + (py[i] - 0.5) ** 2, i
        )
    )
    starts = []
    if n <= 35:
        starts = list(range(n))
    else:
        for q in range(10):
            starts.append(center_order[q * (n - 1) // 9])
        starts.extend([
            min(range(n), key=lambda i: (px[i], py[i], i)),
            max(range(n), key=lambda i: (px[i], py[i], -i)),
            min(range(n), key=lambda i: (py[i], px[i], i)),
            max(range(n), key=lambda i: (py[i], px[i], -i)),
            0
        ])
        starts = list(dict.fromkeys(starts))

    seeds = []
    for s in starts:
        seeds.append(nearest_neighbor(s))

    seeds.append(angular_seed(0.5, 0.5))

    # Multiple centers reduce sensitivity to the arbitrary unit-square center.
    if n >= 40:
        for cx, cy in ((0.25, 0.25), (0.25, 0.75),
                       (0.75, 0.25), (0.75, 0.75)):
            seeds.append(angular_seed(cx, cy))

    insertion_starts = starts if n <= 35 else starts[:5]
    for s in insertion_starts:
        seeds.append(insertion_seed(s))

    best = None
    best_value = float("inf")

    for seed in seeds:
        t = improve(seed)
        value = tour_length(t)
        if value < best_value:
            best_value = value
            best = t

    # Intensify the strongest tour with bounded segment relocations and 2-opt.
    t = best[:]
    for _ in range(3):
        old_value = tour_length(t)
        t = relocate(t, 2, (1, 2, 3))
        t = two_opt(t, True, 30)
        new_value = tour_length(t)
        if new_value >= old_value - 1e-12:
            break
        if new_value < best_value:
            best_value = new_value
            best = t[:]

    # A final unrestricted pass gives small instances thorough refinement.
    if n <= 60:
        t = two_opt(best, False, 30)
        t = two_opt(t, True, 30)
        if tour_length(t) < best_value:
            best = t

    return [int(i) for i in best]
