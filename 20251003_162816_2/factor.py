import sys
n=int(sys.argv[1]) if len(sys.argv)>1 else int(sys.stdin.readline())
f=[]
d=2
while d*d<=n:
    while n%d==0:
        f.append(d); n//=d
    d+=1 if d==2 else 2
if n>1: f.append(n)
print(*f)
