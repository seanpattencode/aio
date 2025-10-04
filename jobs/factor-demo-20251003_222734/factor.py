#!/usr/bin/env python3
import sys
n=int(sys.argv[1])
f=[];d=2
while d*d<=n:
    while n%d==0:f.append(d);n//=d
    d+=1 if d==2 else 2
if n>1:f.append(n)
print(f or [int(sys.argv[1])])
