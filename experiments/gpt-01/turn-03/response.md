```python
import math


def solve(points):
    n = len(points)
    if n <= 2:
        return list(range(n))

    px = [float(p[0]) for p in points]
    py = [float(p[1]) for p in points]

    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i):
            d = math.hypot(px[i] - px[j], py[i] - py[j])
            dist[i][j] = dist[j][i] = d

    k = min(n - 1, max(16, min(32, n // 2 + 8)))
    near = []
    for i in range(n):
        near.append(sorted(
            (j for j in range(n) if j != i),
            key=lambda j: (dist[i][j], j)
        )[:k])

    def tour_length(t):
        return sum(dist[t[i]][t[(i + 1) % n]] for i in range(n))

    def positions(t):
        pos = [0] * n
        for i, v in enumerate(t):
            pos[v] = i
        return pos

    def two_opt(tour, candidate=True, max_passes=60):
        t = tour[:]
        pos = positions(t)

        for _ in range(max_passes):
            changed = False
            for i in range(n - 2):
                a = t[i]
                b = t[i + 1]
                dab = dist[a][b]
                cs = near[a] if candidate else range(n)

                for c in cs:
                    j = pos[c]
                    if j <= i + 1 or j >= n:
                        continue
                    d = t[(j + 1) % n]

                    if dist[a][c] + dist[b][d] >= dab + dist[c][d] - 1e-12:
                        continue

                    t[i + 1:j + 1] = reversed(t[i + 1:j + 1])
                    for q in range(i + 1, j + 1):
                        pos[t[q]] = q
                    changed = True
                    break

                if changed:
                    break

            if not changed:
                # Handle the closing edge by rotating the tour.
                a = t[-1]
                b = t[0]
                for c in near[a] if candidate else range(n):
                    j = pos[c]
                    if j <= 0 or j >= n - 1:
                        continue
                    d = t[(j + 1) % n]
                    if dist[a][c] + dist[b][d] < dist[a][b] + dist[c][d] - 1e-12:
                        t = t[j + 1:] + t[:j + 1]
                        pos = positions(t)
                        changed = True
                        break

            if not changed:
                break

        return t

    def relocate(tour, max_passes=4, block_sizes=(1, 2, 3)):
        t = tour[:]

        for _ in range(max_passes):
            pos = positions(t)
            changed = False

            for size in block_sizes:
                if size >= n - 2:
                    continue

                for i in range(n - size + 1):
                    block = t[i:i + size]
                    first = block[0]
                    last = block[-1]
                    a = t[(i - 1) % n]
                    b = t[(i + size) % n]

                    removed = dist[a][first] + dist[last][b] - dist[a][b]
                    internal = 0.0
                    for q in range(size - 1):
                        internal += dist[block[q]][block[q + 1]]

                    best_delta = -1e-12
                    best_j = -1

                    candidates = set()
                    for v in block:
                        candidates.update(near[v])

                    for c in candidates:
                        j = pos[c]
                        if i <= j < i + size:
                            continue

                        u = t[(j - 1) % n]
                        w = t[j]

                        delta = (
                            dist[a][b]
                            + dist[u][first]
                            + dist[last][w]
                            - dist[a][first]
                            - dist[last][b]
                            - dist[u][w]
                        )

                        if delta < best_delta:
                            best_delta = delta
                            best_j = j

                    if best_j >= 0:
                        del t[i:i + size]
                        c = tour[best_j]
                        try:
                            jj = t.index(c)
                        except ValueError:
                            jj = min(best_j, len(t))
                        t[jj:jj] = block
                        changed = True
                        break

                if changed:
                    break

            if not changed:
                break

        return t

    def nearest_neighbor(start):
        used = [False] * n
        used[start] = True
        t = [start]
        cur = start

        for _ in range(n - 1):
            best = -1
            bestd = float("inf")

            for j in near[cur]:
                if not used[j] and dist[cur][j] < bestd:
                    best = j
                    bestd = dist[cur][j]

            if best < 0:
                for j in range(n):
                    if not used[j] and dist[cur][j] < bestd:
                        best = j
                        bestd = dist[cur][j]

            t.append(best)
            used[best] = True
            cur = best

        return t

    def convex_hull():
        order = sorted(range(n), key=lambda i: (px[i], py[i], i))
        if n <= 2:
            return order

        def cross(o, a, b):
            return (
                (px[a] - px[o]) * (py[b] - py[o])
                - (py[a] - py[o]) * (px[b] - px[o])
            )

        lower = []
        for v in order:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], v) <= 0:
                lower.pop()
            lower.append(v)

        upper = []
        for v in reversed(order):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], v) <= 0:
                upper.pop()
            upper.append(v)

        hull = lower[:-1] + upper[:-1]
        if len(hull) < 3:
            return order
        return hull

    def insertion_seed(start, farthest=True):
        used = [False] * n
        chosen = [start]
        used[start] = True

        second = max(
            (j for j in range(n) if j != start),
            key=lambda j: (dist[start][j], -j)
        )
        chosen.append(second)
        used[second] = True

        mind = [min(dist[i][start], dist[i][second]) for i in range(n)]

        while len(chosen) < n:
            if farthest:
                v = max(
                    (j for j in range(n) if not used[j]),
                    key=lambda j: (mind[j], -j)
                )
            else:
                v = min(
                    (j for j in range(n) if not used[j]),
                    key=lambda j: (mind[j], j)
                )

            m = len(chosen)
            best_delta = float("inf")
            best_i = 0

            for i in range(m):
                a = chosen[i]
                b = chosen[(i + 1) % m]
                delta = dist[a][v] + dist[v][b] - dist[a][b]
                if delta < best_delta:
                    best_delta = delta
                    best_i = i + 1

            chosen.insert(best_i, v)
            used[v] = True

            for j in range(n):
                if not used[j] and dist[j][v] < mind[j]:
                    mind[j] = dist[j][v]

        return chosen

    def improve(t):
        t = two_opt(t, candidate=False, max_passes=16)
        t = two_opt(t, candidate=True, max_passes=45)
        t = relocate(t, max_passes=3, block_sizes=(1, 2))
        t = two_opt(t, candidate=True, max_passes=30)
        t = relocate(t, max_passes=2, block_sizes=(1, 2, 3))
        t = two_opt(t, candidate=True, max_passes=25)
        return t

    starts = sorted(
        range(n),
        key=lambda i: (
            (px[i] - 0.5) ** 2 + (py[i] - 0.5) ** 2,
            i
        )
    )

    if n <= 35:
        chosen_starts = list(range(n))
    else:
        chosen_starts = [
            starts[q * (n - 1) // 11] for q in range(12)
        ]
        chosen_starts += [
            min(range(n), key=lambda i: (px[i], py[i], i)),
            max(range(n), key=lambda i: (px[i], py[i], -i)),
            min(range(n), key=lambda i: (py[i], px[i], i)),
            max(range(n), key=lambda i: (py[i], px[i], -i)),
            0, n // 4, n // 2, 3 * n // 4
        ]
        chosen_starts = list(dict.fromkeys(chosen_starts))

    seeds = []

    for start in chosen_starts:
        seeds.append(nearest_neighbor(start))

    hull = convex_hull()
    seeds.append(hull)

    # Insert remaining cities in cheapest-insertion order into the hull.
    hull_used = [False] * n
    for v in hull:
        hull_used[v] = True

    tour = hull[:]
    while len(tour) < n:
        best_delta = float("inf")
        best_v = -1
        best_i = 0

        for v in range(n):
            if hull_used[v]:
                continue

            for i in range(len(tour)):
                a = tour[i]
                b = tour[(i + 1) % len(tour)]
                delta = dist[a][v] + dist[v][b] - dist[a][b]
                if delta < best_delta:
                    best_delta = delta
                    best_v = v
                    best_i = i + 1

        tour.insert(best_i, best_v)
        hull_used[best_v] = True

    seeds.append(tour)

    for start in chosen_starts[::max(1, len(chosen_starts) // 4)]:
        seeds.append(insertion_seed(start, True))

    geometric = sorted(
        range(n),
        key=lambda i: (
            math.atan2(py[i] - 0.5, px[i] - 0.5),
            (px[i] - 0.5) ** 2 + (py[i] - 0.5) ** 2,
            i
        )
    )
    seeds.append(geometric)

    best_tour = list(range(n))
    best_len = float("inf")

    for seed in seeds:
        t = improve(seed)
        value = tour_length(t)

        if value < best_len:
            best_len = value
            best_tour = t

    return [int(i) for i in best_tour]
```