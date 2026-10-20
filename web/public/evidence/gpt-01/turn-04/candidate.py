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

    k = min(n - 1, 24)
    near = [
        sorted(
            (j for j in range(n) if j != i),
            key=lambda j: (dist[i][j], j)
        )[:k]
        for i in range(n)
    ]

    def tour_length(t):
        return sum(dist[t[i]][t[(i + 1) % n]] for i in range(n))

    def make_pos(t):
        pos = [0] * n
        for i, v in enumerate(t):
            pos[v] = i
        return pos

    def two_opt(tour, candidate=True, max_passes=60):
        t = tour[:]
        pos = make_pos(t)

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
                    if j == n - 1 and i == 0:
                        continue

                    d = t[(j + 1) % n]
                    delta = dist[a][c] + dist[b][d] - dab - dist[c][d]

                    if delta < -1e-12:
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

    def relocate(tour, block_sizes=(1, 2, 3), max_passes=5):
        t = tour[:]

        for _ in range(max_passes):
            pos = make_pos(t)
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

                    internal = 0.0
                    for q in range(size - 1):
                        internal += dist[block[q]][block[q + 1]]

                    removed_delta = (
                        dist[a][b]
                        - dist[a][first]
                        - dist[last][b]
                        + internal
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
                                removed_delta
                                + dist[u][first]
                                + dist[last][w]
                                - dist[u][w]
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
                        min_d[x] + 0.2 * max(dist[x][t[0]], dist[x][t[-1]]),
                        -x
                    )
                )
            else:
                v = min(
                    remaining,
                    key=lambda x: (
                        min(
                            dist[x][t[q]] + dist[x][t[(q + 1) % len(t)]]
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
                    best_i = i + 1

            t.insert(best_i, v)
            used[v] = True

            for j in remaining:
                if not used[j]:
                    min_d[j] = min(min_d[j], dist[j][v])

        return t

    def angular_seed(cx, cy):
        return sorted(
            range(n),
            key=lambda i: (
                math.atan2(py[i] - cy, px[i] - cx),
                (px[i] - cx) ** 2 + (py[i] - cy) ** 2,
                i
            )
        )

    def improve(t, full_passes=5, candidate_passes=35, reloc_passes=3):
        t = two_opt(t, candidate=False, max_passes=full_passes)
        t = two_opt(t, candidate=True, max_passes=candidate_passes)
        t = relocate(t, max_passes=reloc_passes)
        t = two_opt(t, candidate=True, max_passes=20)
        return t

    candidates = []

    # Angular orders around multiple deterministic centers.
    centers = [
        (0.5, 0.5),
        (sum(px) / n, sum(py) / n),
        (min(px), min(py)),
        (min(px), max(py)),
        (max(px), min(py)),
        (max(px), max(py)),
    ]

    for cx, cy in centers:
        candidates.append(angular_seed(cx, cy))

    # Nearest-neighbor tours from spatially diverse starting cities.
    radial = sorted(
        range(n),
        key=lambda i: (
            (px[i] - 0.5) ** 2 + (py[i] - 0.5) ** 2,
            i
        )
    )

    start_ids = set()
    count = min(n, 10 if n >= 60 else 12)
    for q in range(count):
        start_ids.add(radial[q * (n - 1) // max(1, count - 1)])
    start_ids.update([0, n // 4, n // 2, 3 * n // 4, n - 1])

    for s in sorted(start_ids):
        candidates.append(nearest_neighbor(s))

    # Farthest-point and cheapest-insertion seeds.
    for mode in range(3):
        candidates.append(insertion_seed(radial[0], mode))
        if mode < 2:
            candidates.append(insertion_seed(radial[-1], mode))

    best_tour = list(range(n))
    best_len = tour_length(best_tour)

    for idx, seed in enumerate(candidates):
        # Spend more effort on promising initial tours.
        t = two_opt(seed, candidate=False, max_passes=12 if n >= 70 else 20)
        t = two_opt(t, candidate=True, max_passes=35)
        if idx % 2 == 0:
            t = relocate(t, max_passes=3)
            t = two_opt(t, candidate=True, max_passes=20)

        value = tour_length(t)
        if value < best_len:
            best_len = value
            best_tour = t

    # A final stronger local search on the incumbent.
    t = two_opt(best_tour, candidate=False, max_passes=30)
    t = two_opt(t, candidate=True, max_passes=50)
    t = relocate(t, block_sizes=(1, 2, 3), max_passes=5)
    t = two_opt(t, candidate=True, max_passes=30)

    if tour_length(t) < best_len:
        best_tour = t

    return [int(v) for v in best_tour]
