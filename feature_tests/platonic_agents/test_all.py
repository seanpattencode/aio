#!/usr/bin/env python3
"""Test harness: one prompt to each agent, check if ls works."""
import subprocess as S,os
D=os.path.dirname(os.path.abspath(__file__))
PY="/home/seanpatten/micromamba/bin/python3"
E={k:v for k,v in os.environ.items()if k!="CLAUDECODE"}
agents=[("gemini_agent",15),("claude_agent",30),("meta_agent",45)]
for name,t in agents:
    print(f"\n{'='*40}\n[{name}]")
    try:
        r=S.run([PY,f"{D}/{name}.py"],input="list files in current directory\n\n",capture_output=1,text=1,timeout=t,env=E,cwd=D)
        out=r.stdout.strip();cmd="CMD:"in out;ls=any(f in out for f in["agent.py","REPORT"])
        print(out[:500]if out else"(empty)")
        print(f"-> {'PASS'if cmd and ls else'FAIL'} cmd={cmd} ls={ls}")
    except S.TimeoutExpired:print("-> TIMEOUT")
    except Exception as e:print(f"-> ERROR: {e}")
