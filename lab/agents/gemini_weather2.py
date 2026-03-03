#!/usr/bin/env python3
import subprocess,shutil,os,re
gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'NYC weather. Reply ONLY: <temp>NUMBER</temp><feels>NUMBER</feels><cond>WORD</cond>'],capture_output=True,text=True,timeout=120)
t=re.search(r'<temp>(\d+)</temp>',r.stdout)
f=re.search(r'<feels>(\d+)</feels>',r.stdout)
c=re.search(r'<cond>(\w+)</cond>',r.stdout)
print(f"{t[1]}°F (feels {f[1]}°F) {c[1]}" if t and f and c else r.stdout)
