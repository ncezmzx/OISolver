import sys

line = sys.stdin.readline()
if not line:
    raise SystemExit(2)
int(line)
print("? 1", flush=True)
answer = sys.stdin.readline().strip()
if not answer:
    raise SystemExit(3)
print("! {}".format(answer), flush=True)
