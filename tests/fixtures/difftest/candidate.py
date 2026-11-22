import bisect
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
if not data:
    raise SystemExit(2)
n, values = data[0], data[1:]
if len(values) != n:
    raise SystemExit(2)
tails = []
for value in values:
    place = bisect.bisect_right(tails, value)  # Deliberate strict-LIS bug.
    if place == len(tails):
        tails.append(value)
    else:
        tails[place] = value
print(len(tails))
