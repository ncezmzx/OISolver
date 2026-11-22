import itertools
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
if not data:
    raise SystemExit(2)
n, values = data[0], data[1:]
if len(values) != n:
    raise SystemExit(2)
best = 0
for mask in range(1 << n):
    chosen = [values[i] for i in range(n) if mask >> i & 1]
    if all(chosen[i] < chosen[i + 1] for i in range(len(chosen) - 1)):
        best = max(best, len(chosen))
print(best)
