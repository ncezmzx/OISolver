import os
import random

seed = int(os.environ.get("OISOLVER_SEED", "1"))
rng = random.Random(seed)
n = rng.randint(2, 8)
q = rng.randint(6, 18)
values = [rng.randint(-5, 5) for _ in range(n)]
operations = []
queries = 0
for i in range(q):
    kind = rng.choices(("add", "set", "query"), weights=(4, 3, 4))[0]
    if i == q - 1 and queries == 0:
        kind = "query"
    left = rng.randrange(n)
    right = rng.randrange(left, n) + 1
    if kind == "query":
        operations.append((kind, left, right))
        queries += 1
    else:
        operations.append((kind, left, right, rng.randint(-5, 5)))
print(n, q)
print(*values)
for operation in operations:
    print(*operation)
