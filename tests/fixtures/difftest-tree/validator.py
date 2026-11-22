import sys

try:
    rows = [line.split() for line in sys.stdin.read().splitlines() if line.strip()]
    n = int(rows[0][0])
    assert len(rows[0]) == 1 and 1 <= n <= 20 and len(rows) == n + 1
    weights = list(map(int, rows[1]))
    assert len(weights) == n and all(-20 <= value <= 20 for value in weights)
    adjacency = [[] for _ in range(n + 1)]
    seen_edges = set()
    for row in rows[2:]:
        assert len(row) == 3
        u, v, weight = map(int, row)
        assert 1 <= u <= n and 1 <= v <= n and u != v and -20 <= weight <= 20
        edge = tuple(sorted((u, v)))
        assert edge not in seen_edges
        seen_edges.add(edge)
        adjacency[u].append(v)
        adjacency[v].append(u)
    seen = {1}
    stack = [1]
    while stack:
        node = stack.pop()
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    assert len(seen) == n and len(seen_edges) == n - 1
except (AssertionError, IndexError, ValueError):
    raise SystemExit(1)
