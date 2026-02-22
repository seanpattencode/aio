#!/usr/bin/env python3
"""Meta agent: parallel LLM calls, fused response."""
import subprocess as S,os,sys
from concurrent.futures import ThreadPoolExecutor,as_completed

E={k:v for k,v in os.environ.items()if k!="CLAUDECODE"}
SYS="Linux CLI. ENTIRE reply: CMD: <cmd>. After output, plain text."
m=[]

def ask_claude(p):
    r=S.run(["claude","-p"],input=p,capture_output=1,text=1,env=E)
    return"claude",r.stdout.strip()

def ask_gemini(p):
    r=S.run(["gemini","-p",p],capture_output=1,text=1)
    return"gemini",r.stdout.strip()

while u:=input("\n> ").strip():
    m+=[f"User: {u}"];ran=set()
    for _ in range(5):
        p=SYS+"\n\n"+"\n".join(m[-20:])
        with ThreadPoolExecutor(2)as ex:
            results=dict(f.result()for f in as_completed([ex.submit(ask_claude,p),ex.submit(ask_gemini,p)]))
        for name in("claude","gemini"):
            print(f"[{name}] {results[name]}\n")
        # use claude as primary for CMD, show both for comparison
        t=results["claude"]
        m+=[f"Assistant: {t}"]
        if"CMD:"not in t:break
        c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")
        if c in ran:break
        ran.add(c);print(f"$ {c}")
        try:r=S.run(c,shell=1,capture_output=1,text=1,timeout=30);o=(r.stdout+r.stderr).strip()
        except Exception as e:o=str(e)
        print(o or"(no output)");m+=[f"User: `{c}`:\n{o or'(no output)'}"]
