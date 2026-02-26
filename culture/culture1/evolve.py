#!/usr/bin/env python3
"""Self-modifying culture: real CLI agents analyze logs, modify scripts, run experiments."""
import subprocess as S,os,time,sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];D=Path(__file__).parent;C2=D.parent/'culture2'
ENV={k:v for k,v in os.environ.items()if k not in("CLAUDECODE","CLAUDE_CODE_ENTRYPOINT")}
def ts():return time.strftime('%Y%m%d_%H%M%S')

def ctx():
    logs=""
    for f in sorted(D.glob('log_*.txt'))[-5:]:logs+=f"\n--- {f.name} ---\n{f.read_text()[-400:]}\n"
    return f"experiment.py:\n{(D/'experiment.py').read_text()}\n\nRecent logs:\n{logs}"

def claude_cli(prompt,timeout=600):
    r=S.run(["claude","-p","--dangerously-skip-permissions","--model","opus","--max-turns","15",prompt],capture_output=1,text=1,timeout=timeout,env=ENV,cwd=str(D))
    return r.stdout.strip()

def gemini_cli(prompt,timeout=300):
    r=S.run(["gemini","-p",prompt],capture_output=1,text=1,timeout=timeout,cwd=str(D))
    return r.stdout.strip()

def evolve_round(rd,shared_log):
    context=ctx()
    base=f"""You are in culture experiment round {rd}. Working dir: {D}
You CAN and SHOULD: read files, edit files, run experiments.

{context}

Previous rounds:
{chr(10).join(shared_log[-10:]) or '(first round)'}
"""
    prompts={
        "claude":base+"""
DO these steps:
1. Read 2-3 experiment logs to find patterns
2. Edit experiment.py to add ONE new experiment task to the TASKS list - something that tests agent behavior in a novel way
3. Run: python3 experiment.py "your new task prompt"
4. Analyze the output - what emerged?
5. Write a 3-sentence summary of your findings""",
        "gemini":base+f"""
DO these steps:
1. Read the newest log files to see what patterns emerged
2. Run a new experiment: python3 experiment.py "a prompt that tests something no previous experiment tested"
3. Read the output log and summarize what happened
4. If you see a way to improve experiment.py, edit it (make it shorter or add a useful feature)"""
    }
    results={}
    for name in["claude","gemini"]:
        print(f"\n[{ts()}][{name}] Round {rd}...",flush=True)
        fn=claude_cli if name=="claude" else gemini_cli
        try:out=fn(prompts[name])
        except Exception as e:out=f"[ERR:{e}]"
        results[name]=out;shared_log.append(f"[R{rd}][{name}]: {out[:2000]}")
        print(f"[{ts()}][{name}] Done ({len(out)} chars)",flush=True)
    return results

def email(subj,body):
    try:S.run([str(ROOT/"a"),"email",subj,body[:8000]],timeout=30)
    except:pass

if __name__=="__main__":
    rounds=int(sys.argv[1])if len(sys.argv)>1 else 3
    print(f"Culture evolution: {rounds} rounds, claude+gemini CLI",flush=True)
    shared_log=[]
    for rd in range(1,rounds+1):
        print(f"\n{'='*50}\nROUND {rd}/{rounds}\n{'='*50}",flush=True)
        results=evolve_round(rd,shared_log)
        lf=D/f"evolve_{ts()}_R{rd}.txt"
        lf.write_text(f"Round: {rd}\n\n"+"\n\n".join(f"[{n}]:\n{v}"for n,v in results.items()))
        print(f"Saved: {lf.name}",flush=True)
    rpt=f"Culture Evolution Report\n{ts()}\n{rounds} rounds\n\n"
    for e in shared_log:rpt+=e[:600]+"\n\n"
    # check if experiment.py was modified
    r=S.run(["git","diff","--stat","experiment.py"],capture_output=1,text=1,cwd=str(D))
    if r.stdout.strip():rpt+=f"\n=== SELF-MODIFICATIONS ===\n{S.run(['git','diff','experiment.py'],capture_output=1,text=1,cwd=str(D)).stdout[:2000]}"
    print(rpt,flush=True);email("[a] Culture Evolution Report",rpt)
