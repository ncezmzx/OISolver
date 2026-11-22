import sys

try:
    lines = [line.split() for line in sys.stdin.read().splitlines() if line.strip()]
    n, q = map(int, lines[0])
    values = list(map(int, lines[1]))
    assert 2 <= n <= 20 and 1 <= q <= 100 and len(values) == n and len(lines) == q + 2
    for row in lines[2:]:
        assert row[0] in ("add", "set", "query")
        assert len(row) == (3 if row[0] == "query" else 4)
        left, right = int(row[1]), int(row[2])
        assert 0 <= left < right <= n
        if len(row) == 4:
            int(row[3])
except (AssertionError, IndexError, ValueError):
    raise SystemExit(1)
