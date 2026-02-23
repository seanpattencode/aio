#!/usr/bin/env python3
"""10-model fusion: each model votes once on a random pair, aggregate wins."""
import subprocess as S,json,random;from multiprocessing.pool import ThreadPool as TP;from urllib.request import urlopen as U,Request as Rq;from collections import Counter
P=__import__('pathlib').Path;KF={l.split('=',1)[0]:l.split('=',1)[1].strip()for l in open(P(__file__).resolve().parents[2]/'adata'/'git'/'login'/'api_keys.env')if'='in l}
Q="You are a Linux CLI agent. Reply ONLY with CMD:<shell command> to run commands, or plain text answer. Never refuse."
OR="https://openrouter.ai/api/v1/chat/completions";OK=KF["OPENROUTER_API_KEY"]

def oai(url,key,model,p,sys=Q):
    try:return json.loads(U(Rq(url,json.dumps({"model":model,"max_tokens":1024,"messages":[{"role":"system","content":sys},{"role":"user","content":p}]}).encode(),{"Authorization":"Bearer "+key,"Content-Type":"application/json"}),timeout=30).read())["choices"][0]["message"]["content"].strip()
    except Exception as e:return f"[ERR:{e}]"

def anth(p):
    try:return json.loads(U(Rq("https://api.anthropic.com/v1/messages",json.dumps({"model":"claude-opus-4-6","max_tokens":1024,"system":Q,"messages":[{"role":"user","content":p}]}).encode(),{"x-api-key":KF["ANTHROPIC_API_KEY"],"anthropic-version":"2023-06-01","content-type":"application/json"}),timeout=30).read())["content"][0]["text"].strip()
    except Exception as e:return f"[ERR:{e}]"

def gem(p):
    try:return json.loads(U(Rq(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={KF['GOOGLE_API_KEY']}",json.dumps({"contents":[{"parts":[{"text":Q+"\n"+p}]}]}).encode(),{"Content-Type":"application/json"}),timeout=30).read())["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:return f"[ERR:{e}]"

# (name, response_fn, openrouter_id for judging)
MS=[("claude",anth,"anthropic/claude-opus-4-6"),("gemini",gem,"google/gemini-2.5-flash"),
    ("gpt",lambda p:oai("https://api.openai.com/v1/chat/completions",KF["OPENAI_API_KEY"],"gpt-4.1",p),"openai/gpt-4.1"),
    ("deepseek",lambda p:oai("https://api.deepseek.com/chat/completions",KF["DEEPSEEK_API_KEY"],"deepseek-chat",p),"deepseek/deepseek-chat"),
    ("grok",lambda p:oai(OR,OK,"x-ai/grok-4",p),"x-ai/grok-4"),
    ("mistral",lambda p:oai(OR,OK,"mistralai/mistral-large-2512",p),"mistralai/mistral-large-2512"),
    ("qwen",lambda p:oai(OR,OK,"qwen/qwen3-235b-a22b-07-25",p),"qwen/qwen3-235b-a22b-07-25"),
    ("kimi",lambda p:oai(OR,OK,"moonshotai/kimi-k2.5",p),"moonshotai/kimi-k2.5"),
    ("glm",lambda p:oai(OR,OK,"z-ai/glm-4.7-20251222",p),"z-ai/glm-4.7-20251222"),
    ("ds-r1",lambda p:oai(OR,OK,"deepseek/deepseek-r1",p),"deepseek/deepseek-r1")]

def fuse(R,q,judge_ids):
    """10 judges, each votes on a random pair. Returns (winner_name, wins_counter)."""
    names=list(R.keys())
    matchups=[(jid,*random.sample(names,2))for jid in judge_ids]
    def j(m):
        jid,a,b=m
        v=oai(OR,OK,jid,f"Q:{q}\nA:{R[a][:500]}\nB:{R[b][:500]}","Pick the better response. Reply ONLY A or B.")
        return a if"A"in v[:3]else b
    wins=Counter(TP(10).map(j,matchups))
    return wins

m=[]
while u:=input("\n> ").strip():
    m+=[f"U:{u}"];p="\n".join(m[-20:])
    for _ in[0]*3:
        R=dict(TP(10).starmap(lambda n,f,_,p:(n,f(p)),[(n,f,o,p)for n,f,o in MS]))
        for n in sorted(R):print(f"[{n}] {R[n][:200]}")
        oids=[o for _,_,o in MS]
        # cross-vote: each frontier model judges one random pair
        w1=fuse(R,u,oids)
        print("\n--- cross-vote ---")
        for n,v in w1.most_common():print(f"  {v} votes: [{n}]")
        # cheap-vote: gpt-4.1-mini judges 10 random pairs
        w2=fuse(R,u,["openai/gpt-4.1-mini"]*10)
        print("--- cheap-vote ---")
        for n,v in w2.most_common():print(f"  {v} votes: [{n}]")
        # drive execution from top cross-vote winner
        top=w1.most_common(1)[0][0]
        t=R[top];m+=[f"A:{t}"];c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[f"OUTPUT of `{c}`:\n{o or'(empty)'}\nNow give a plain text answer."];p="\n".join(m[-20:])
