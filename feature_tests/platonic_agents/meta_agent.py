#!/usr/bin/env python3
import subprocess as S,anthropic;from multiprocessing.pool import ThreadPool
P=__import__('pathlib').Path;A=anthropic.Anthropic(api_key=next(l.split('=',1)[1].strip()for l in open(P(__file__).resolve().parents[2]/'adata'/'git'/'login'/'api_keys.env')if'ANTHROP'in l));Q="Linux CLI. Reply: CMD:<cmd> or text.";m=[]
def ask(n,p):return n,S.run(["gemini","-p",Q+"\n"+p],capture_output=1,text=1).stdout.strip()if n>"d"else A.messages.create(model="claude-sonnet-4-6",max_tokens=1024,system=Q,messages=[{"role":"user","content":p}]).content[0].text.strip()
while u:=input("\n> ").strip():
    m+=[f"U:{u}"];p="\n".join(m[-20:])
    for _ in[0]*3:
        R=dict(ThreadPool(2).starmap(ask,[("claude",p),("gemini",p)]))
        for n in R:print(f"[{n}] {R[n]}\n")
        t=R["claude"];m+=[f"A:{t}"];c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[f"U:{o}"]
