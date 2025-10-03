n=int(input())
i=2
f=[]
while i*i<=n:
    while n%i==0:
        f.append(i); n//=i
    i+=1 if i==2 else 2
if n>1: f.append(n)
print(*f)
