import sys

lines = [line.split() for line in sys.stdin.read().splitlines() if line.strip()]
n, q = map(int, lines[0])
values = list(map(int, lines[1]))
if len(values) != n or len(lines) != q + 2:
    raise SystemExit(2)
size = 4 * n
sums = [0] * size
adds = [0] * size
sets = [0] * size
has_set = [False] * size


def build(node, left, right):
    if right - left == 1:
        sums[node] = values[left]
        return
    middle = (left + right) // 2
    build(node * 2, left, middle)
    build(node * 2 + 1, middle, right)
    sums[node] = sums[node * 2] + sums[node * 2 + 1]


def apply_add(node, left, right, amount):
    sums[node] += amount * (right - left)
    if has_set[node]:
        sets[node] += amount
    else:
        adds[node] += amount


def apply_set(node, left, right, amount):
    sums[node] = amount * (right - left)
    has_set[node] = True
    sets[node] = amount
    # Deliberate bug: an older pending add must be cleared here.


def push(node, left, right):
    if right - left == 1:
        has_set[node] = False
        adds[node] = 0
        return
    middle = (left + right) // 2
    if has_set[node]:
        apply_set(node * 2, left, middle, sets[node])
        apply_set(node * 2 + 1, middle, right, sets[node])
        has_set[node] = False
    if adds[node]:
        apply_add(node * 2, left, middle, adds[node])
        apply_add(node * 2 + 1, middle, right, adds[node])
        adds[node] = 0


def update(node, left, right, ql, qr, amount, assignment):
    if ql <= left and right <= qr:
        (apply_set if assignment else apply_add)(node, left, right, amount)
        return
    push(node, left, right)
    middle = (left + right) // 2
    if ql < middle:
        update(node * 2, left, middle, ql, qr, amount, assignment)
    if middle < qr:
        update(node * 2 + 1, middle, right, ql, qr, amount, assignment)
    sums[node] = sums[node * 2] + sums[node * 2 + 1]


def query(node, left, right, ql, qr):
    if ql <= left and right <= qr:
        return sums[node]
    push(node, left, right)
    middle = (left + right) // 2
    result = 0
    if ql < middle:
        result += query(node * 2, left, middle, ql, qr)
    if middle < qr:
        result += query(node * 2 + 1, middle, right, ql, qr)
    return result


build(1, 0, n)
answers = []
for row in lines[2:]:
    kind, left, right = row[0], int(row[1]), int(row[2])
    if kind == "query":
        answers.append(query(1, 0, n, left, right))
    else:
        update(1, 0, n, left, right, int(row[3]), kind == "set")
print(*answers)
