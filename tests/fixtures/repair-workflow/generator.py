import argparse
import random
parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=int, required=True)
args = parser.parse_args()
rng = random.Random(args.seed)
n = rng.randint(1, 7)
values = [rng.randint(-5, 5) for _ in range(n - 1)] + [rng.randint(1, 5)]
print(n)
print(*values)
