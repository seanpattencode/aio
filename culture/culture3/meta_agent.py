#!/usr/bin/env python3
import subprocess as S,json;from multiprocessing.pool import ThreadPool;from urllib.request import urlopen as U,Request as Rq
P=__import__('pathlib').Path;K=next(l.split('=',1)[1].strip()for l in open(P(__file__).resolve().parents[2]/'adata'/'git'/'login'/'api_keys.env')if'ANTHROP'in l);Q="You are a Linux CLI agent. You MUST reply ONLY with CMD:<shell command> to run commands. After seeing output, give a text answer. Never refuse or explain.";m=[]
def ask(n,p):return n,S.run(["gemini","-p","Reply CMD:<cmd> or text.\n"+p],capture_output=1,text=1).stdout.strip()if n>"d"else json.loads(U(Rq("https://api.anthropic.com/v1/messages",json.dumps({"model":"claude-opus-4-6","max_tokens":1024,"system":Q,"messages":[{"role":"user","content":p}]}).encode(),{"x-api-key":K,"anthropic-version":"2023-06-01","content-type":"application/json"})).read())["content"][0]["text"]
while u:=input("\n> ").strip():
    m+=[f"U:{u}"];p="\n".join(m[-20:])
    for _ in[0]*3:
        R=dict(ThreadPool(2).starmap(ask,[("claude",p),("gemini",p)]))
        for n in R:print(f"[{n}] {R[n]}\n")
        t=R["claude"];m+=[f"A:{t}"];c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[f"OUTPUT of `{c}`:\n{o or'(empty)'}"]
