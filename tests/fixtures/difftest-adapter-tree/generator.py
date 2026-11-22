import argparse
import random


parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=int, required=True)
args = parser.parse_args()
rng = random.Random(args.seed)

# Counted input, 0-indexed vertices, and non-canonical edge order w u v.
print(3)
print(5)
for w, u, v in [(2, 0, 1), (9, 1, 2), (3, 1, 3), (4, 3, 4)]:
    print(w, u, v)
print(3)
for w, u, v in [(1, 0, 1), (2, 1, 2)]:
    print(w, u, v)
print(4)
for w, u, v in [(5, 0, 1), (6, 0, 2), (7, 2, 3)]:
    print(w, u, v)
