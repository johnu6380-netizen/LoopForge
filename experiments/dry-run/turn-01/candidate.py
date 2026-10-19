import math
import random


def solve(points):
    n = len(points)
    if n <= 2:
        return list(range(n))

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            d = math.hypot(dx, dy)
            dist[i][j] = d
            dist[j][i] = d

    if n <= 3:
        return list(range(n))

    def length(tour):
        return sum(dist[tour[i]][tour[(i + 1) % n]]
                   for i in range(n))

    def two_opt(tour, max_passes=100):
        tour = tour[:]
        for _ in range(max_passes):
            improved = False
            for i in range(n - 2):
                a = tour[i]
                b = tour[i + 1]
                for j in range(i + 2, n if i > 0 else n - 1):
                    c = tour[j]
                    d = tour[(j + 1) % n]
                    delta = dist[a][c] + dist[b][d] - dist[a][b] - dist[c][d]
                    if delta < -1e-12:
                        tour[i + 1:j + 1] = reversed(tour[i + 1:j + 1])
                        improved = True
                        break
                if improved:
                    break
            if not improved:
                break
        return tour

    def nearest_neighbor(start):
        unvisited = set(range(n))
        unvisited.remove(start)
        tour = [start]
        current = start

        while unvisited:
            nxt = min(unvisited, key=lambda j: (dist[current][j], j))
            unvisited.remove(nxt)
            tour.append(nxt)
            current = nxt

        return tour

    def insertion_tour(start):
        remaining = set(range(n))
        remaining.remove(start)

        second = min(remaining, key=lambda j: (dist[start][j], j))
        remaining.remove(second)
        tour = [start, second]

        while remaining:
            best_delta = float("inf")
            best_city = -1
            best_pos = -1

            for city in remaining:
                for pos in range(len(tour)):
                    a = tour[pos]
                    b = tour[(pos + 1) % len(tour)]
                    delta = dist[a][city] + dist[city][b] - dist[a][b]
                    if delta < best_delta - 1e-15 or (
                        abs(delta - best_delta) <= 1e-15
                        and (city, pos) < (best_city, best_pos)
                    ):
                        best_delta = delta
                        best_city = city
                        best_pos = pos

            tour.insert(best_pos + 1, best_city)
            remaining.remove(best_city)

        return tour

    def candidate_two_opt(tour, candidates, max_passes=60):
        tour = tour[:]

        for _ in range(max_passes):
            pos = [0] * n
            for i, city in enumerate(tour):
                pos[city] = i

            improved = False

            for i in range(n):
                a = tour[i]
                b = tour[(i + 1) % n]

                for c in candidates[a]:
                    j = pos[c]
                    if j == i or j == (i + 1) % n:
                        continue

                    if (j + 1) % n == i:
                        continue

                    if j < i:
                        ii, jj = j, i
                        aa = tour[ii]
                        bb = tour[ii + 1]
                        cc = tour[jj]
                        dd = tour[(jj + 1) % n]
                    else:
                        ii, jj = i, j
                        aa, bb, cc, dd = a, b, tour[j], tour[(j + 1) % n]

                    if jj == ii + 1:
                        continue

                    delta = dist[aa][cc] + dist[bb][dd] - dist[aa][bb] - dist[cc][dd]

                    if delta < -1e-12:
                        tour[ii + 1:jj + 1] = reversed(tour[ii + 1:jj + 1])
                        improved = True
                        break

                if improved:
                    break

            if not improved:
                break

        return tour

    k = min(n - 1, 18)
    candidates = []
    for i in range(n):
        candidates.append(sorted(
            (j for j in range(n) if j != i),
            key=lambda j: (dist[i][j], j)
        )[:k])

    starts = list(range(n))
    starts.sort(key=lambda i: (
        xs[i] + ys[i],
        xs[i],
        ys[i],
        i
    ))

    selected = []
    for idx in range(min(n, 12)):
        selected.append(starts[idx * n // min(n, 12)])

    selected.extend([
        min(range(n), key=lambda i: (xs[i], ys[i], i)),
        max(range(n), key=lambda i: (xs[i], ys[i], -i)),
        min(range(n), key=lambda i: (ys[i], xs[i], i)),
        max(range(n), key=lambda i: (ys[i], xs[i], -i))
    ])
    selected = list(dict.fromkeys(selected))

    best_tour = None
    best_len = float("inf")

    for start in selected:
        tour = two_opt(nearest_neighbor(start), max_passes=80)
        tour_len = length(tour)
        if tour_len < best_len:
            best_len = tour_len
            best_tour = tour

    insertion_starts = sorted(
        range(n),
        key=lambda i: (
            -(abs(xs[i] - 0.5) + abs(ys[i] - 0.5)),
            i
        )
    )[:min(n, 5)]

    for start in insertion_starts:
        tour = two_opt(insertion_tour(start), max_passes=80)
        tour_len = length(tour)
        if tour_len < best_len:
            best_len = tour_len
            best_tour = tour

    tour = candidate_two_opt(best_tour, candidates, max_passes=80)
    tour_len = length(tour)
    if tour_len < best_len:
        best_len = tour_len
        best_tour = tour

    # A final full 2-opt pass removes any remaining nonlocal crossings.
    tour = two_opt(best_tour, max_passes=100)
    if length(tour) < best_len:
        best_tour = tour

    return [int(i) for i in best_tour]
