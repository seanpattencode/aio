#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'-p','Search for new frontier AI model releases (GPT, Claude, Gemini, Llama, etc) in last 3 days. Reply ONLY: <new>YES or NO</new><model>name if new else NONE</model><company>company</company><info>key info 15 words max</info>'],capture_output=True,text=True,timeout=120)
n,m,c,i=re.search(r'<new>(\w+)</new>',r.stdout),re.search(r'<model>([^<]+)</model>',r.stdout),re.search(r'<company>([^<]+)</company>',r.stdout),re.search(r'<info>([^<]+)</info>',r.stdout)
if n and n[1].upper()=='YES' and m and m[1]!='NONE':
    msg=f"New Model: {m[1]} ({c[1].strip() if c else ''})\n\n{i[1].strip() if i else ''}"
    print(msg)
    save("g-frontier",msg)
    if "--send" in sys.argv: send("New Frontier Model",msg)
else:
    print("No new frontier models")
