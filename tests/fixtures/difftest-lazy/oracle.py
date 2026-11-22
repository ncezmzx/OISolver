import sys

lines = [line.split() for line in sys.stdin.read().splitlines() if line.strip()]
n, q = map(int, lines[0])
values = list(map(int, lines[1]))
if len(values) != n or len(lines) != q + 2:
    raise SystemExit(2)
answers = []
for row in lines[2:]:
    kind, left, right = row[0], int(row[1]), int(row[2])
    if kind == "query":
        answers.append(sum(values[left:right]))
    else:
        amount = int(row[3])
        for index in range(left, right):
            values[index] = values[index] + amount if kind == "add" else amount
print(*answers)
