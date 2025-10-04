n=int(input())
f=[]
d=2
while d*d<=n:
    if n%d==0:f.append(d);n//=d
    else:d+=1
if n>1:f.append(n)
print(*f)
