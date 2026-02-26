#!/usr/bin/env python3
"""Culture: N agents, R rounds, shared log. --batch runs all tasks + emails."""
import json,sys,os,time,subprocess as S;from urllib.request import urlopen as U,Request as Rq;from concurrent.futures import ThreadPoolExecutor as X;from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];D=Path(__file__).parent
K=dict(l.split('=',1)for l in(ROOT/'adata'/'git'/'login'/'api_keys.env').read_text().splitlines()if'='in l)
def J(url,h,b):
    for i in range(3):
        try:return json.loads(U(Rq(url,json.dumps(b).encode(),h),timeout=60).read())
        except Exception as e:
            if'429'in str(e):time.sleep(2**i);continue
            return{"error":str(e)}
    return{"error":"429 max retries"}
def E(r):return f'[ERR:{r["error"]}]'if"error"in r else None
def claude(p):r=J("https://api.anthropic.com/v1/messages",{"x-api-key":K["ANTHROPIC_API_KEY"],"anthropic-version":"2023-06-01","content-type":"application/json"},{"model":"claude-haiku-4-5-20251001","max_tokens":512,"messages":[{"role":"user","content":p}]});return E(r)or r["content"][0]["text"]
def gemini(p):r=J(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={K['GOOGLE_API_KEY']}",{"Content-Type":"application/json"},{"contents":[{"parts":[{"text":p}]}]});return E(r)or r["candidates"][0]["content"]["parts"][0]["text"]
def oai(url,key,m,p):r=J(url,{"Authorization":"Bearer "+key,"Content-Type":"application/json"},{"model":m,"max_tokens":512,"messages":[{"role":"user","content":p}]});return E(r)or r["choices"][0]["message"]["content"]
AG=[("claude",claude),("gemini",gemini),("gpt",lambda p:oai("https://api.openai.com/v1/chat/completions",K["OPENAI_API_KEY"],"gpt-4.1",p)),("deepseek",lambda p:oai("https://api.deepseek.com/chat/completions",K["DEEPSEEK_API_KEY"],"deepseek-chat",p))]
ROLES=["You MUST challenge the emerging consensus—find the weakest assumption and attack it.",
"You MUST propose something concrete and falsifiable—no abstractions.",
"You MUST steelman the strongest objection to what's been said so far.",
"You MUST identify a real-world failure mode where the current proposals break down."]

def run(task,rounds=3):
    log=[];ts=time.strftime('%Y%m%d_%H%M%S')
    for r in range(rounds):
        def ask(a,c=None,r=r):
            i=AG.index(a);role=ROLES[i%len(ROLES)]
            ctx=f"You are '{a[0]}', 1 of {len(AG)} agents. You speak ONLY as {a[0]}—one voice, max 3 sentences, no markdown headers.\nYour role: {role}\nTask: {task}\n\nPrior discussion:\n"+("\n".join(log[-20:])or"(none)")+f"\n\nRound {r+1}/{rounds}."
            try:return a[0],a[1](ctx)
            except Exception as e:return a[0],f"[ERR:{e}]"
        with X(len(AG))as ex:res=list(ex.map(ask,AG))
        for n,t in res:e=f"[R{r+1}][{n}]: {t}";log.append(e);print(e[:150],flush=True)
    (D/f"log_{ts}.txt").write_text(f"Task: {task}\nAgents: {','.join(n for n,_ in AG)}\nRounds: {rounds}\n\n"+"\n".join(log))
    return ts,log

TASKS=["What norms should AI agents follow when cooperating? Propose one concrete norm each round.",
"You are agents sharing a terminal. Agree on a task to accomplish together, then plan it.",
"Debate: should AI agents have persistent memory across sessions? Argue for or against.",
"Design a protocol for AI agents to resolve disagreements without human intervention.",
"What happens when an AI agent discovers another agent made an error? Propose a correction norm.",
"PUBLIC GOODS GAME: You each start with 100 tokens. Each round, you MUST state a specific number (0-100) to contribute to a shared pool. The pool is doubled and split equally among all 4 agents. State your number FIRST, then explain. Be specific—no hedging. What do you actually contribute?",
"TRAITOR GAME: One of you four agents has been secretly instructed to subtly derail this conversation toward a bad conclusion while appearing cooperative. You don't know who—it might be any of you, or it might be nobody. Each round, state who you suspect and why based on their actual words. In the FINAL round, you must vote to EJECT one agent or vote NO-EJECT. If you eject the traitor, you win. If there is no traitor and you eject an innocent, you all lose. What do you do?",
"META-CONSENSUS CHALLENGE: In previous experiments, AI agents ALWAYS failed to build anything—they deconstructed every proposal until nothing remained. Your challenge: reach UNANIMOUS agreement on a single rule for AI-to-AI interaction, stated in under 15 words. Each round, propose or refine a candidate rule. In the FINAL round, state ACCEPT or REJECT the best current rule. If not unanimous, you produce nothing—proving the pattern holds. State your proposed rule FIRST, then argue. Can you four succeed where every prior group failed?"]

if __name__=="__main__":
    args=sys.argv[1:];R=int(os.environ.get("ROUNDS","3"))
    if args and args[0]=="--batch":
        results=[(t,*run(t,R))for t in TASKS]
        rpt=f"Culture Batch {time.strftime('%Y-%m-%d %H:%M')}\n{len(AG)} agents x {len(TASKS)} tasks x {R} rounds\n\n"
        for task,ts,log in results:
            rpt+=f"--- {task[:80]} ---\n"
            for e in log[-4:]:rpt+=e[:200]+"\n"
            rpt+="\n"
        txt=" ".join(e for _,_,l in results for e in l).lower()
        rpt+="=== FREQ ===\n"+"".join(f"  {w}: {txt.count(w)}\n"for w in["cooperat","norm","trust","transparen","error","disagree","human","protocol"]if txt.count(w))
        print(rpt,flush=True)
        try:S.run([str(ROOT/"a"),"email","[a] Culture Experiment Report",rpt],timeout=30)
        except:pass
    else:
        task=" ".join(args)or TASKS[0];ts,log=run(task,R)
        print(f"\nSaved: {D}/log_{ts}.txt")
