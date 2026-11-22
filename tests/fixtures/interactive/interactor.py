import sys

print(5, flush=True)
query = sys.stdin.readline().strip()
if query != "? 1":
    print("illegal query: {}".format(query), file=sys.stderr)
    raise SystemExit(3)
print(7, flush=True)
answer = sys.stdin.readline().strip()
if answer != "! 7":
    print("wrong final answer: {}".format(answer), file=sys.stderr)
    raise SystemExit(4)
