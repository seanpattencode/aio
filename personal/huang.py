#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'-p','Search for recent Jensen Huang (NVIDIA CEO) quotes or insights from last 7 days. Reply ONLY: <found>YES or NO</found><quote>quote text if found</quote><context>event/interview name 10 words max</context><date>date</date>'],capture_output=True,text=True,timeout=120)
f,q,c,d=re.search(r'<found>(\w+)</found>',r.stdout),re.search(r'<quote>([^<]+)</quote>',r.stdout),re.search(r'<context>([^<]+)</context>',r.stdout),re.search(r'<date>([^<]+)</date>',r.stdout)
if f and f[1].upper()=='YES' and q and q[1].strip():
    msg=f'"{q[1].strip()}"\n\n- Jensen Huang, {c[1].strip() if c else ""} ({d[1].strip() if d else ""})'
    print(msg)
    save("g-huang",msg)
    if "--send" in sys.argv: send("Jensen Huang Quote",msg)
else:
    print("No recent Huang quotes found")
