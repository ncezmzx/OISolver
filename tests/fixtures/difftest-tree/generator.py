import os
import random

seed = int(os.environ.get("OISOLVER_SEED", "1"))
rng = random.Random(seed)
n = 8
weights = [rng.randint(-9, 9) for _ in range(n)]
if weights[-1] == 0:
    weights[-1] = 7
edges = []
for vertex in range(2, n + 1):
    parent = rng.randrange(1, vertex)
    weight = rng.randint(-9, 9)
    edges.append((parent, vertex, weight))
print(n)
print(*weights)
for edge in edges:
    print(*edge)
