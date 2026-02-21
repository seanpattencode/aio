#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'-p','Motivate someone building AI agent tools. Reply ONLY: <msg>2 sentences why it matters</msg><quote>inspiring tech quote</quote><by>author</by>'],capture_output=True,text=True,timeout=240)
m,q,a=re.search(r'<msg>([^<]+)</msg>',r.stdout),re.search(r'<quote>([^<]+)</quote>',r.stdout),re.search(r'<by>([^<]+)</by>',r.stdout)
msg=f"{m[1].strip()}\n\n\"{q[1].strip()}\"\n- {a[1].strip()}" if m and q and a else r.stdout.strip()
print(msg)
save("g-motivate",msg)
if "--send" in sys.argv: send("Keep Building",msg)
