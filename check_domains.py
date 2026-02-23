import socket
from concurrent.futures import ThreadPoolExecutor as E

T="ai,sh,io,do,run,dev,app,so,is,to,me,cc,co,tv,us,in,it,be,at,ch,de,fr,nl,se,no,fi,dk,pl,cz,sk,hu,ro,bg,hr,si,lt,lv,ee,pt,es,ie,uk,ca,mx,br,ar,cl,jp,kr,tw,hk,sg,au,nz,za,ke,ng,gh,ma,il,ae,pk,th,vn,ph,my,xyz,tech,net,org,info,pro,one,gg,lol,wtf,fyi,tools,zone,cloud,code,systems,works,world,life,live,space,site,online,digital,software".split(',')

def c(t):
 try: socket.getaddrinfo(f"aio.{t}",80); return t,0
 except: return t,1

with E(30) as e: r=list(e.map(c,T))
a=[f"aio.{t}" for t,v in r if v]
x=[f"aio.{t}" for t,v in r if not v]

print(f"Checking {len(T)} TLDs\n\nAvailable ({len(a)}):")
for d in a: print(f" ✓ {d}")
print(f"\nTaken ({len(x)}):")
for d in x: print(f"   {d}")
print(f"\n{len(a)} avail / {len(x)} taken / {len(T)} total")