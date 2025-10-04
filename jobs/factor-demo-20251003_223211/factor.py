#!/usr/bin/env python3
import sys
n=int(sys.argv[1]) if len(sys.argv)>1 else int(input())
f=[];d=2
while d*d<=n:
    while n%d==0:f.append(d);n//=d
    d+=1
if n>1:f.append(n)
print(*f)
