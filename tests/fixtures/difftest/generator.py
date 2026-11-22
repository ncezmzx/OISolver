import os
import random

seed = int(os.environ.get("OISOLVER_SEED", "1"))
rng = random.Random(seed)
n = rng.randint(3, 9)
value = rng.randint(-5, 5)
values = [value, value] + [rng.randint(-5, 5) for _ in range(n - 2)]
print(n)
print(*values)
