#!/usr/bin/env python3
import subprocess as S,ollama,sys;M,m=sys.argv[1]if len(sys.argv)>1 else"mistral",[]
while u:=input("\n> ").strip():
    m+=[{"role":"user","content":u}]
    for _ in[0]*5:
        t=ollama.chat(M,[{"role":"system","content":"Linux CLI. ENTIRE reply: CMD:<cmd>. After output, text."}]+m[-20:]).message.content.strip();print(t);m+=[{"role":"assistant","content":t}];c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[{"role":"user","content":f"`{c}`:\n{o or'~'}"}]
