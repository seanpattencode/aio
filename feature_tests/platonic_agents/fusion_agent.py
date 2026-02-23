#!/usr/bin/env python3
"""10-model fusion: cross-vote (diverse judges) + cheap-vote (fast judge). One parallel step each."""
import subprocess as S,json,random;from multiprocessing.pool import ThreadPool as TP;from urllib.request import urlopen as U,Request as Rq
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

# (name, response_fn, openrouter_id_for_judging)
MS=[("claude",anth,"anthropic/claude-opus-4-6"),("gemini",gem,"google/gemini-2.5-flash"),
    ("gpt",lambda p:oai("https://api.openai.com/v1/chat/completions",KF["OPENAI_API_KEY"],"gpt-4.1",p),"openai/gpt-4.1"),
    ("deepseek",lambda p:oai("https://api.deepseek.com/chat/completions",KF["DEEPSEEK_API_KEY"],"deepseek-chat",p),"deepseek/deepseek-chat"),
    ("grok",lambda p:oai(OR,OK,"x-ai/grok-4",p),"x-ai/grok-4"),
    ("mistral",lambda p:oai(OR,OK,"mistralai/mistral-large-2512",p),"mistralai/mistral-large-2512"),
    ("qwen",lambda p:oai(OR,OK,"qwen/qwen3-235b-a22b-07-25",p),"qwen/qwen3-235b-a22b-07-25"),
    ("kimi",lambda p:oai(OR,OK,"moonshotai/kimi-k2.5",p),"moonshotai/kimi-k2.5"),
    ("glm",lambda p:oai(OR,OK,"z-ai/glm-4.7-20251222",p),"z-ai/glm-4.7-20251222"),
    ("ds-r1",lambda p:oai(OR,OK,"deepseek/deepseek-r1",p),"deepseek/deepseek-r1")]

def vote(pairs,jids,q):
    """5 binary judgments in parallel. Returns [(winner_name, response)]."""
    def j(i):
        (na,ra),(nb,rb)=pairs[i]
        v=oai(OR,OK,jids[i],f"Q:{q}\nA:{ra[:500]}\nB:{rb[:500]}","Pick the better response. Reply ONLY A or B.")
        return(na,ra)if"A"in v[:3]else(nb,rb)if"B"in v[:3]else(na,ra)
    return list(TP(5).map(j,range(5)))

m=[]
while u:=input("\n> ").strip():
    m+=[f"U:{u}"];p="\n".join(m[-20:])
    for _ in[0]*3:
        R=dict(TP(10).starmap(lambda n,f,_,p:(n,f(p)),[(n,f,o,p)for n,f,o in MS]))
        for n in sorted(R):print(f"[{n}] {R[n][:200]}")
        # pair responses randomly
        items=list(R.items());random.shuffle(items)
        pairs=[(items[i],items[i+1])for i in range(0,10,2)]
        oids={n:o for n,_,o in MS}
        # method 1: cross-vote — each pair judged by model from a different pair
        jx=[oids[items[(i*2+2)%10][0]]for i in range(5)]
        w1=vote(pairs,jx,u)
        print(f"\n--- cross-vote ---")
        for n,_ in w1:print(f"  W [{n}]")
        # method 2: cheap-vote — one fast model judges all pairs
        w2=vote(pairs,["openai/gpt-4.1-mini"]*5,u)
        print(f"--- cheap-vote ---")
        for n,_ in w2:print(f"  W [{n}]")
        # drive execution from cross-vote winners, prefer claude
        t=next((r for n,r in w1 if n=="claude"),w1[0][1])
        m+=[f"A:{t}"];c=t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""
        if not c:break
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[f"OUTPUT of `{c}`:\n{o or'(empty)'}\nNow give a plain text answer."];p="\n".join(m[-20:])
