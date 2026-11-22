import sys


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


tokens = sys.stdin.buffer.read().split()
if not tokens:
    fail("empty input")
pos = 0
try:
    t = int(tokens[pos])
    pos += 1
    if not 1 <= t <= 4:
        fail("bad test count")
    for _ in range(t):
        n = int(tokens[pos])
        pos += 1
        if not 1 <= n <= 8:
            fail("bad n")
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for _ in range(n - 1):
            w, u, v = map(int, tokens[pos:pos + 3])
            pos += 3
            if not 1 <= w <= 20 or not 0 <= u < n or not 0 <= v < n or u == v:
                fail("bad edge")
            ru, rv = find(u), find(v)
            if ru == rv:
                fail("cycle")
            parent[ru] = rv
        if n > 1 and len({find(i) for i in range(n)}) != 1:
            fail("disconnected")
except (ValueError, IndexError):
    fail("malformed")
if pos != len(tokens):
    fail("trailing tokens")
