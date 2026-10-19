def solve(points):
    """Greedy baseline: always walk to the closest unvisited city."""
    n = len(points)
    if n == 0:
        return []
    tour = [0]
    unvisited = set(range(1, n))
    current = 0
    while unvisited:
        cx, cy = points[current]
        current = min(unvisited, key=lambda j: ((points[j][0] - cx) ** 2 + (points[j][1] - cy) ** 2, j))
        unvisited.remove(current)
        tour.append(current)
    return tour
