#!/usr/bin/env python3
import subprocess as S,os;E={k:v for k,v in os.environ.items()if k!="CLAUDECODE"};m=[]
while u:=input("> "):
    m+=f"U:{u}",
    for _ in[0]*3:
        t=S.run(["claude","-p","--tools","","--system-prompt","Reply CMD:<cmd> or text.","\n".join(m[-20:])],capture_output=1,text=1,env=E).stdout.strip();print(t);m+=f"A:{t}",;c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=f"U:{o}",
