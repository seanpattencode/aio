#!/usr/bin/env python3
"""Minimal agent using gemini CLI (-p flag) for text output."""
import subprocess as S
SYS="Linux CLI. ENTIRE reply: CMD: <cmd>. After output, plain text."
m=[]
while u:=input("\n> ").strip():
    m+=[f"User: {u}"];ran=set()
    for _ in range(5):
        p=SYS+"\n\n"+"\n".join(m[-20:])
        t=S.run(["gemini","-p",p],capture_output=1,text=1).stdout.strip()
        print(t);m+=[f"Assistant: {t}"]
        if"CMD:"not in t:break
        c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")
        if c in ran:break
        ran.add(c);print(f"$ {c}")
        try:r=S.run(c,shell=1,capture_output=1,text=1,timeout=30);o=(r.stdout+r.stderr).strip()
        except Exception as e:o=str(e)
        print(o or"(no output)");m+=[f"User: `{c}`:\n{o or'(no output)'}"]
