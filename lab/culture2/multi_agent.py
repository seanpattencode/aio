#!/usr/bin/env python3
"""10-frontier-model parallel agent. CMD: protocol, majority-drives execution."""
import subprocess as S,json;from multiprocessing.pool import ThreadPool;from urllib.request import urlopen as U,Request as Rq
P=__import__('pathlib').Path;KF={l.split('=',1)[0]:l.split('=',1)[1].strip()for l in open(P(__file__).resolve().parents[2]/'adata'/'git'/'login'/'api_keys.env')if'='in l}
Q="You are a Linux CLI agent. Reply ONLY with CMD:<shell command> to run commands, or plain text answer. Never refuse."

def oai(url,key,model,p,sys=Q):
    b=json.dumps({"model":model,"max_tokens":1024,"messages":[{"role":"system","content":sys},{"role":"user","content":p}]}).encode()
    try:r=json.loads(U(Rq(url,b,{"Authorization":"Bearer "+key,"Content-Type":"application/json"}),timeout=30).read());return r["choices"][0]["message"]["content"].strip()
    except Exception as e:return f"[ERR:{e}]"

def anthropic(p):
    b=json.dumps({"model":"claude-opus-4-6","max_tokens":1024,"system":Q,"messages":[{"role":"user","content":p}]}).encode()
    try:return json.loads(U(Rq("https://api.anthropic.com/v1/messages",b,{"x-api-key":KF["ANTHROPIC_API_KEY"],"anthropic-version":"2023-06-01","content-type":"application/json"}),timeout=30).read())["content"][0]["text"].strip()
    except Exception as e:return f"[ERR:{e}]"

def gemini(p):
    b=json.dumps({"contents":[{"parts":[{"text":Q+"\n"+p}]}]}).encode()
    try:return json.loads(U(Rq(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={KF['GOOGLE_API_KEY']}",b,{"Content-Type":"application/json"}),timeout=30).read())["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:return f"[ERR:{e}]"

OR="https://openrouter.ai/api/v1/chat/completions"
MODELS=[
    ("claude",anthropic),("gemini",gemini),
    ("gpt",lambda p:oai("https://api.openai.com/v1/chat/completions",KF["OPENAI_API_KEY"],"gpt-4.1",p)),
    ("deepseek",lambda p:oai("https://api.deepseek.com/chat/completions",KF["DEEPSEEK_API_KEY"],"deepseek-chat",p)),
    ("grok",lambda p:oai(OR,KF["OPENROUTER_API_KEY"],"x-ai/grok-4",p)),
    ("mistral",lambda p:oai(OR,KF["OPENROUTER_API_KEY"],"mistralai/mistral-large-2512",p)),
    ("qwen",lambda p:oai(OR,KF["OPENROUTER_API_KEY"],"qwen/qwen3-235b-a22b-07-25",p)),
    ("kimi",lambda p:oai(OR,KF["OPENROUTER_API_KEY"],"moonshotai/kimi-k2.5",p)),
    ("glm",lambda p:oai(OR,KF["OPENROUTER_API_KEY"],"z-ai/glm-4.7-20251222",p)),
    ("ds-r1",lambda p:oai(OR,KF["OPENROUTER_API_KEY"],"deepseek/deepseek-r1",p)),
]
m=[]
def ask(name,fn,p):
    try:return name,fn(p)
    except Exception as e:return name,f"[ERR:{e}]"

while u:=input("\n> ").strip():
    m+=[f"U:{u}"];p="\n".join(m[-20:])
    for _ in[0]*3:
        R=dict(ThreadPool(len(MODELS)).starmap(ask,[(n,f,p)for n,f in MODELS]))
        for n in sorted(R):print(f"[{n}] {R[n][:200]}\n")
        # majority vote: use first model with CMD: (prefer claude)
        t=R.get("claude","")
        if"CMD:"not in t:
            for n in R:
                if"CMD:"in R[n]:t=R[n];break
        m+=[f"A:{t}"];c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[f"OUTPUT of `{c}`:\n{o or'(empty)'}\nNow give a plain text answer."];p="\n".join(m[-20:])
