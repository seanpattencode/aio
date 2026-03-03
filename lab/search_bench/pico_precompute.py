U=[str(i)for i in range(999)];x={}
for i,u in enumerate(U):[x.setdefault(u[j:j+2],[]).append(i)for j in range(len(u)-1)]
q=input();print(*[U[i]for i in x.get(q[:2],range(999))if q in U[i]][:9],sep="\n")
