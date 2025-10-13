#!/usr/bin/env python3
import sys
n=int(sys.argv[1]) if len(sys.argv)>1 else int(input("n: "))
f=[]
d=2
while d*d<=n:
    while n%d==0: f.append(d); n//=d
    d=3 if d==2 else d+2
if n>1: f.append(n)
print(*f)
