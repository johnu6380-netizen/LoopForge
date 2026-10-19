```python
import math


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

    k = min(n - 1, 28 if n < 60 else 24)
    near = [
        sorted((j for j in range(n) if j != i),
               key=lambda j: (dist[i][j], j))[:k]
        for i in range(n)
    ]

    def tour_length(t):
        return sum(dist[t[i]][t[(i + 1) % n]] for i in range(n))

    def make_pos(t):
        pos = [0] * n
        for i, v in enumerate(t):
            pos[v] = i
        return pos

    def two_opt(t, candidate=True, max_passes=100, best_improvement=False):
        t = t[:]
        pos = make_pos(t)

        for _ in range(max_passes):
            changed = False
            best_delta = -1e-12
            best_i = best_j = -1

            for i in range(n - 1):
                a = t[i]
                b = t[(i + 1) % n]
                cs = near[a] if candidate else range(n)

                for c in cs:
                    j = pos[c]
                    if j <= i + 1 or j >= n:
                        continue
                    if i == 0 and j == n - 1:
                        continue

                    d = t[(j + 1) % n]
                    delta = (
                        dist[a][c] + dist[b][d]
                        - dist[a][b] - dist[c][d]
                    )

                    if delta < best_delta:
                        best_delta = delta
                        best_i, best_j = i, j
                        if not best_improvement:
                            break

                if best_i >= 0 and not best_improvement:
                    break

            if best_i < 0:
                break

            l, r = best_i + 1, best_j
            t[l:r + 1] = reversed(t[l:r + 1])
            for q in range(l, r + 1):
                pos[t[q]] = q
            changed = True

            if not changed:
                break

        return t

    def relocate(t, max_passes=4, block_sizes=(1, 2, 3)):
        t = t[:]

        for _ in range(max_passes):
            pos = make_pos(t)
            improved = False

            for size in block_sizes:
                if size >= n - 2:
                    continue

                for i in range(n):
                    if i + size > n:
                        continue

                    block = t[i:i + size]
                    first, last = block[0], block[-1]
                    a = t[(i - 1) % n]
                    b = t[(i + size) % n]

                    removed = (
                        dist[a][b] - dist[a][first]
                        - dist[last][b]
                    )
                    for q in range(size - 1):
                        removed += dist[block[q]][block[q + 1]]

                    best_delta = -1e-12
                    best_c = -1

                    for v in block:
                        for c in near[v]:
                            j = pos[c]
                            if i <= j < i + size:
                                continue

                            u = t[(j - 1) % n]
                            w = t[j]
                            delta = (
                                removed + dist[u][first]
                                + dist[last][w] - dist[u][w]
                            )

                            if delta < best_delta:
                                best_delta = delta
                                best_c = c

                    if best_c >= 0:
                        del t[i:i + size]
                        j = t.index(best_c)
                        t[j:j] = block
                        improved = True
                        break

                if improved:
                    break

            if not improved:
                break

        return t

    def nearest_neighbor(start):
        unused = [True] * n
        unused[start] = False
        t = [start]
        cur = start

        for _ in range(n - 1):
            best = -1
            best_d = float("inf")

            for j in near[cur]:
                if unused[j] and dist[cur][j] < best_d:
                    best = j
                    best_d = dist[cur][j]

            if best < 0:
                for j in range(n):
                    if unused[j] and dist[cur][j] < best_d:
                        best = j
                        best_d = dist[cur][j]

            t.append(best)
            unused[best] = False
            cur = best

        return t

    def insertion_seed(start, mode=0):
        used = [False] * n
        used[start] = True

        second = max(
            (j for j in range(n) if j != start),
            key=lambda j: (dist[start][j], -j)
        )
        t = [start, second]
        used[second] = True
        min_d = [min(dist[v][start], dist[v][second]) for v in range(n)]

        while len(t) < n:
            remaining = [v for v in range(n) if not used[v]]

            if mode == 0:
                v = max(remaining, key=lambda x: (min_d[x], -x))
            elif mode == 1:
                v = max(
                    remaining,
                    key=lambda x: (
                        min_d[x] + 0.2 * max(
                            dist[x][t[0]], dist[x][t[-1]]
                        ),
                        -x
                    )
                )
            else:
                v = min(
                    remaining,
                    key=lambda x: (
                        min(
                            dist[x][t[q]]
                            + dist[x][t[(q + 1) % len(t)]]
                            - dist[t[q]][t[(q + 1) % len(t)]]
                            for q in range(len(t))
                        ),
                        x
                    )
                )

            best_delta = float("inf")
            best_i = 0

            for i in range(len(t)):
                a = t[i]
                b = t[(i + 1) % len(t)]
                delta = dist[a][v] + dist[v][b] - dist[a][b]
                if delta < best_delta:
                    best_delta = delta
                    best_i = i

            t.insert(best_i + 1, v)
            used[v] = True

            for x in remaining:
                if not used[x]:
                    min_d[x] = min(min_d[x], dist[x][v])

        return t

    def improve(t, rounds=2):
        t = two_opt(t, candidate=False, max_passes=60,
                    best_improvement=True)
        t = two_opt(t, candidate=True, max_passes=80)
        for _ in range(rounds):
            t = relocate(t, max_passes=2, block_sizes=(1, 2, 3))
            t = two_opt(t, candidate=True, max_passes=40)
        return t

    center_order = sorted(
        range(n),
        key=lambda i: (
            math.atan2(py[i] - 0.5, px[i] - 0.5), i
        )
    )

    starts = sorted(
        range(n),
        key=lambda i: (
            (px[i] - 0.5) ** 2 + (py[i] - 0.5) ** 2, i
        )
    )

    if n <= 35:
        chosen = list(range(n))
    else:
        chosen = [starts[q * (n - 1) // 11] for q in range(12)]
        chosen.extend([0, n // 4, n // 2, 3 * n // 4])
        chosen = list(dict.fromkeys(chosen))

    seeds = [center_order]
    for start in chosen:
        seeds.append(nearest_neighbor(start))

    if n <= 70:
        seeds.append(insertion_seed(starts[0], 0))
        seeds.append(insertion_seed(starts[-1], 1))
    else:
        seeds.append(insertion_seed(starts[0], 0))

    best_tour = list(range(n))
    best_len = tour_length(best_tour)

    for seed in seeds:
        t = improve(seed, rounds=2)
        value = tour_length(t)

        if value < best_len:
            best_len = value
            best_tour = t

    # A final polishing pass on the best incumbent.
    best_tour = two_opt(
        best_tour, candidate=False, max_passes=80,
        best_improvement=True
    )
    best_tour = two_opt(best_tour, candidate=True, max_passes=60)
    best_tour = relocate(best_tour, max_passes=2, block_sizes=(1, 2, 3))

    return [int(i) for i in best_tour]
```