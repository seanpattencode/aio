#!/usr/bin/env python3
"""Vote-then-run: 10 models propose, vote on reasoning vs cmd-only, then execute winner."""
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

MS=[("claude",anth,"anthropic/claude-opus-4-6"),("gemini",gem,"google/gemini-2.5-flash"),
    ("gpt",lambda p:oai("https://api.openai.com/v1/chat/completions",KF["OPENAI_API_KEY"],"gpt-4.1",p),"openai/gpt-4.1"),
    ("deepseek",lambda p:oai("https://api.deepseek.com/chat/completions",KF["DEEPSEEK_API_KEY"],"deepseek-chat",p),"deepseek/deepseek-chat"),
    ("grok",lambda p:oai(OR,OK,"x-ai/grok-4",p),"x-ai/grok-4"),
    ("mistral",lambda p:oai(OR,OK,"mistralai/mistral-large-2512",p),"mistralai/mistral-large-2512"),
    ("qwen",lambda p:oai(OR,OK,"qwen/qwen3-235b-a22b-07-25",p),"qwen/qwen3-235b-a22b-07-25"),
    ("kimi",lambda p:oai(OR,OK,"moonshotai/kimi-k2.5",p),"moonshotai/kimi-k2.5"),
    ("glm",lambda p:oai(OR,OK,"z-ai/glm-4.7-20251222",p),"z-ai/glm-4.7-20251222"),
    ("ds-r1",lambda p:oai(OR,OK,"deepseek/deepseek-r1",p),"deepseek/deepseek-r1")]

def extract_cmd(t):return t[t.index("CMD:")+4:].split("\n")[0].strip(" `")if"CMD:"in t else""

def vote(view,q,judge_ids):
    """10 judges vote on random pairs from view dict. Returns Counter."""
    names=list(view.keys());matchups=[(jid,*random.sample(names,2))for jid in judge_ids]
    def j(m):
        jid,a,b=m
        v=oai(OR,OK,jid,f"Q:{q}\nA:{view[a][:500]}\nB:{view[b][:500]}","Which proposal better answers the question? Reply ONLY A or B.")
        return a if"A"in v[:3]else b
    return Counter(TP(10).map(j,matchups))

m=[]
while u:=input("\n> ").strip():
    m+=[f"U:{u}"];p="\n".join(m[-20:])
    for _ in[0]*3:
        # step 1: all 10 models propose
        R=dict(TP(10).starmap(lambda n,f,_,p:(n,f(p)),[(n,f,o,p)for n,f,o in MS]))
        cmds={n:extract_cmd(R[n])for n in R}
        for n in sorted(R):print(f"[{n}] {R[n][:200]}")
        # skip voting if no CMD: from anyone
        if not any(cmds.values()):m+=[f"A:{R.get('claude',list(R.values())[0])}"];break
        # step 2: vote BEFORE executing — two views, parallel
        full_view=R  # full reasoning + cmd
        cmd_view={n:f"CMD:{cmds[n]}"for n in cmds if cmds[n]}  # cmd only
        oids=[o for _,_,o in MS]
        v_full,v_cmd=TP(2).starmap(lambda v,q,j:vote(v,q,j),[(full_view,u,oids),(cmd_view,u,oids)])
        print(f"\n--- vote on reasoning+cmd ---")
        for n,v in v_full.most_common():print(f"  {v} votes: [{n}] CMD:{cmds[n]}")
        print(f"--- vote on cmd only ---")
        for n,v in v_cmd.most_common():print(f"  {v} votes: [{n}] CMD:{cmds[n]}")
        # step 3: pick winner — prefer agreement, fallback to full-vote winner
        top_full=v_full.most_common(1)[0][0]
        top_cmd=v_cmd.most_common(1)[0][0]
        winner=top_full if top_full==top_cmd else top_full
        c=cmds[winner]
        print(f"\n>>> [{winner}] wins: CMD:{c}" + (" (both agree)"if top_full==top_cmd else f" (cmd-vote preferred [{top_cmd}])"))
        if not c:m+=[f"A:{R[winner]}"];break
        # step 4: execute only the winning command
        o=S.run(c,shell=1,capture_output=1,text=1,timeout=30).stdout.strip();print(f"${c}\n{o}");m+=[f"A:CMD:{c}",f"OUTPUT of `{c}`:\n{o or'(empty)'}\nNow give a plain text answer."];p="\n".join(m[-20:])
