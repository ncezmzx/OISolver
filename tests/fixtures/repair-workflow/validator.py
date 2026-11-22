import sys
try:
    tokens = list(map(int, sys.stdin.buffer.read().split()))
except ValueError:
    raise SystemExit(1)
if not tokens or not 1 <= tokens[0] <= 7 or len(tokens) != tokens[0] + 1:
    raise SystemExit(1)
if any(not -5 <= value <= 5 for value in tokens[1:]):
    raise SystemExit(1)
