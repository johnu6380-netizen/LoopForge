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

    k = min(n - 1, 28)
    near = [
        sorted((j for j in range(n) if j != i),
               key=lambda j: (dist[i][j], j))[:k]
        for i in range(n)
    ]

    def length(t):
        return sum(dist[t[i]][t[(i + 1) % n]] for i in range(n))

    def positions(t):
        pos = [0] * n
        for i, v in enumerate(t):
            pos[v] = i
        return pos

    def two_opt(tour, candidate=True, max_passes=50):
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
                    if j <= i + 1 or (i == 0 and j == n - 1):
                        continue

                    d = t[(j + 1) % n]
                    if dist[a][c] + dist[b][d] < dab + dist[c][d] - 1e-12:
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

    def relocate(tour, block_sizes=(1, 2, 3), max_passes=4):
        t = tour[:]

        for _ in range(max_passes):
            pos = positions(t)
            changed = False

            for size in block_sizes:
                if size >= n - 2:
                    continue

                for i in range(n - size + 1):
                    block = t[i:i + size]
                    first, last = block[0], block[-1]
                    a = t[(i - 1) % n]
                    b = t[(i + size) % n]

                    internal = sum(
                        dist[block[q]][block[q + 1]]
                        for q in range(size - 1)
                    )
                    removal = (
                        dist[a][b] - dist[a][first]
                        - dist[last][b] + internal
                    )

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
                                removal + dist[u][first]
                                + dist[last][w] - dist[u][w]
                            )

                            if delta < best_delta:
                                best_delta = delta
                                best_c = c

                    if best_c >= 0:
                        del t[i:i + size]
                        j = t.index(best_c)
                        t[j:j] = block
                        changed = True
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
            best_d = float("inf")

            for j in near[cur]:
                if unused[j] and dist[cur][j] < best_d:
                    best, best_d = j, dist[cur][j]

            if best < 0:
                for j in range(n):
                    if unused[j] and dist[cur][j] < best_d:
                        best, best_d = j, dist[cur][j]

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
            else:
                v = max(
                    remaining,
                    key=lambda x: (
                        min_d[x] + 0.15 * max(
                            dist[x][t[0]], dist[x][t[-1]]
                        ),
                        -x
                    )
                )

            best_delta = float("inf")
            best_i = 0
            m = len(t)

            for i in range(m):
                a, b = t[i], t[(i + 1) % m]
                delta = dist[a][v] + dist[v][b] - dist[a][b]
                if delta < best_delta:
                    best_delta, best_i = delta, i

            t.insert(best_i + 1, v)
            used[v] = True

            for x in remaining:
                min_d[x] = min(min_d[x], dist[x][v])

        return t

    def cheapest_insertion():
        # Begin with a farthest pair and repeatedly insert the city
        # causing the smallest increase in the cycle length.
        a, b = max(
            ((i, j) for i in range(n) for j in range(i)),
            key=lambda pair: (dist[pair[0]][pair[1]], -pair[0], -pair[1])
        )
        t = [a, b]
        used = [False] * n
        used[a] = used[b] = True

        while len(t) < n:
            best_delta = float("inf")
            best_v = -1
            best_i = 0

            for v in range(n):
                if used[v]:
                    continue

                for i in range(len(t)):
                    x, y = t[i], t[(i + 1) % len(t)]
                    delta = dist[x][v] + dist[v][y] - dist[x][y]
                    if delta < best_delta:
                        best_delta, best_v, best_i = delta, v, i

            t.insert(best_i + 1, best_v)
            used[best_v] = True

        return t

    def improve(t):
        t = two_opt(t, candidate=False, max_passes=25)
        t = two_opt(t, candidate=True, max_passes=35)
        t = relocate(t, (1, 2, 3), max_passes=3)
        t = two_opt(t, candidate=True, max_passes=30)
        t = relocate(t, (1, 2), max_passes=2)
        t = two_opt(t, candidate=True, max_passes=20)
        return t

    # Try structurally different deterministic initial tours.
    best = list(range(n))
    best_value = float("inf")

    starts = sorted(
        range(n),
        key=lambda i: (
            (px[i] - 0.5) ** 2 + (py[i] - 0.5) ** 2, i
        )
    )

    if n <= 35:
        selected = list(range(n))
    else:
        selected = [
            starts[q * (n - 1) // 11] for q in range(12)
        ]
        selected.extend([0, n // 4, n // 2, 3 * n // 4])
        selected = list(dict.fromkeys(selected))

    seeds = []
    for s in selected:
        seeds.append(nearest_neighbor(s))

    seeds.append(sorted(
        range(n),
        key=lambda i: (math.atan2(py[i] - 0.5, px[i] - 0.5), i)
    ))
    seeds.append(cheapest_insertion())
    seeds.append(insertion_seed(starts[0], 0))
    seeds.append(insertion_seed(starts[-1], 1))

    # Deduplicate seeds while preserving their deterministic order.
    seen = set()
    unique_seeds = []
    for t in seeds:
        key = tuple(t)
        if key not in seen:
            seen.add(key)
            unique_seeds.append(t)

    for seed in unique_seeds:
        t = improve(seed)
        value = length(t)
        if value < best_value:
            best, best_value = t, value

    return [int(v) for v in best]
