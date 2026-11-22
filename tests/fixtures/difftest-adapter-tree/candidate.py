import sys


def solve_case(tokens, pos):
    n = int(tokens[pos])
    pos += 1
    edges = []
    for _ in range(n - 1):
        w, u, v = map(int, tokens[pos:pos + 3])
        pos += 3
        edges.append((w, u, v))
    # Intentional WA: weighted edges above 7 trigger a one-off error.
    answer = sum(w for w, _u, _v in edges) + int(any(w > 7 for w, _u, _v in edges))
    return answer, pos


data = sys.stdin.buffer.read().split()
pos = 0
t = int(data[pos])
pos += 1
answers = []
for _ in range(t):
    answer, pos = solve_case(data, pos)
    answers.append(str(answer))
print("\n".join(answers))
