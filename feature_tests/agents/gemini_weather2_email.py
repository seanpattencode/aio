#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from agent_base import send

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'NYC weather. Reply ONLY: <temp>NUMBER</temp><feels>NUMBER</feels><cond>WORD</cond>'],capture_output=True,text=True,timeout=120)
t,f,c=re.search(r'<temp>(\d+)</temp>',r.stdout),re.search(r'<feels>(\d+)</feels>',r.stdout),re.search(r'<cond>(\w+)</cond>',r.stdout)
w=f"{t[1]}°F (feels {f[1]}°F) {c[1]}" if t and f and c else "unavailable"
print(f"NYC: {w}")
if "--send" in sys.argv: send("NYC Weather",w)
