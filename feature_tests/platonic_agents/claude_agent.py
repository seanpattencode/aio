#!/usr/bin/env python3
import subprocess as S,anthropic,sys;from pathlib import Path
K=dict(l.split('=',1)for l in(Path(__file__).resolve().parents[2]/'adata'/'git'/'login'/'api_keys.env').read_text().splitlines()if'='in l)
C,M,m=anthropic.Anthropic(api_key=K['ANTHROPIC_API_KEY']),sys.argv[1]if len(sys.argv)>1 else"claude-opus-4-6",[]
while u:=input("\n> ").strip():
    m+=[{"role":"user","content":u}]
    for _ in[0]*5:
        t=C.messages.create(model=M,max_tokens=1024,system="Linux CLI. ENTIRE reply: CMD:<cmd>. After output, text.",messages=m[-20:]).content[0].text.strip();print(t);m+=[{"role":"assistant","content":t}];c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[{"role":"user","content":f"`{c}`:\n{o or'~'}"}]
