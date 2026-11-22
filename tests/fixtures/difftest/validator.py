import sys

try:
    data = list(map(int, sys.stdin.buffer.read().split()))
except ValueError:
    raise SystemExit(1)
if not data:
    raise SystemExit(1)
n, values = data[0], data[1:]
if not (1 <= n <= 20 and len(values) == n and all(-100 <= x <= 100 for x in values)):
    raise SystemExit(1)
