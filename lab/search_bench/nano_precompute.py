import sys,tty,termios as T
U=[f"x{i}"for i in range(9999)]+["chrom"];ix={};q=""
for i,u in enumerate(U):[ix.setdefault(u[j:j+2],[]).append(i)for j in range(len(u)-1)]
o=T.tcgetattr(0);tty.setraw(0)
while(c:=sys.stdin.read(1))not in'\x1b\x03':q=q[:-1]if c=='\x7f'else q+c;print(f"\33[2J>{q}",*[U[i]for i in ix.get(q[:2],range(len(U)))if q in U[i]][:5],sep="\n")
T.tcsetattr(0,0,o)
