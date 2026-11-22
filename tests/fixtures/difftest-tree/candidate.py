import sys

rows = [line.split() for line in sys.stdin.read().splitlines() if line.strip()]
n = int(rows[0][0])
weights = list(map(int, rows[1]))
if len(weights) != n or len(rows) != n + 1:
    raise SystemExit(2)
# Deliberate implementation bug: the final numbered vertex is omitted.
print(sum(weights[:-1]))
