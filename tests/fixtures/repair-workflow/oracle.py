import sys
tokens = list(map(int, sys.stdin.buffer.read().split()))
n = tokens[0]
print(sum(tokens[1:1+n]))
