import sys


def solve_case(tokens, pos):
    n = int(tokens[pos])
    pos += 1
    total = 0
    for _ in range(n - 1):
        w, _u, _v = map(int, tokens[pos:pos + 3])
        pos += 3
        total += w
    return total, pos


data = sys.stdin.buffer.read().split()
pos = 0
t = int(data[pos])
pos += 1
answers = []
for _ in range(t):
    answer, pos = solve_case(data, pos)
    answers.append(str(answer))
print("\n".join(answers))
