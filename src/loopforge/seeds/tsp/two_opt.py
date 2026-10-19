import math


def _nearest_neighbor(points):
    n = len(points)
    tour = [0]
    unvisited = set(range(1, n))
    current = 0
    while unvisited:
        cx, cy = points[current]
        current = min(
            unvisited,
            key=lambda j: ((points[j][0] - cx) ** 2 + (points[j][1] - cy) ** 2, j),
        )
        unvisited.remove(current)
        tour.append(current)
    return tour


def solve(points):
    """Strong reference: nearest neighbor, then 2-opt until no swap helps.

    2-opt repeatedly picks two edges (a,b) and (c,e) and, if replacing them with
    (a,c) and (b,e) shortens the tour, reverses the segment between them.
    """
    n = len(points)
    if n == 0:
        return []
    tour = _nearest_neighbor(points)
    if n < 4:
        return tour

    def d(a, b):
        return math.dist(points[a], points[b])

    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue  # these two edges share a city; skip
                a, b = tour[i], tour[i + 1]
                c, e = tour[j], tour[(j + 1) % n]
                delta = d(a, c) + d(b, e) - d(a, b) - d(c, e)
                if delta < -1e-12:
                    tour[i + 1 : j + 1] = reversed(tour[i + 1 : j + 1])
                    improved = True
    return tour
