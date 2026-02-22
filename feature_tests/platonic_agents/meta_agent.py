#!/usr/bin/env python3
import subprocess as S,os;from concurrent.futures import ThreadPoolExecutor,as_completed
E={k:v for k,v in os.environ.items()if k!="CLAUDECODE"};m=[];P="Linux CLI. ENTIRE reply: CMD:<cmd>. After output, text.\n"
def ask(n,a):return n,S.run(a[:2],input=a[2]if len(a)>2 else None,capture_output=1,text=1,env=E).stdout.strip()
while u:=input("\n> ").strip():
    m+=[f"U:{u}"];p=P+"\n".join(m[-20:])
    for _ in[0]*3:
        with ThreadPoolExecutor(2)as ex:R=dict(f.result()for f in as_completed([ex.submit(ask,"claude",["claude","-p",p]),ex.submit(ask,"gemini",["gemini","-p",p])]))
        for n in R:print(f"[{n}] {R[n]}\n")
        t=R["claude"];m+=[f"A:{t}"];c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[f"U:{o}"]
