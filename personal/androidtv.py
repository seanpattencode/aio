#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'-p','Search for Android TV new version releases in last 7 days. Reply ONLY: <new>YES or NO</new><ver>version if new else NONE</ver><info>key changes 15 words max</info>'],capture_output=True,text=True,timeout=120)
n,v,i=re.search(r'<new>(\w+)</new>',r.stdout),re.search(r'<ver>([^<]+)</ver>',r.stdout),re.search(r'<info>([^<]+)</info>',r.stdout)
if n and n[1].upper()=='YES' and v and v[1]!='NONE':
    msg=f"New Android TV: {v[1]}\n\n{i[1].strip() if i else ''}"
    print(msg)
    save("g-androidtv",msg)
    if "--send" in sys.argv: send("Android TV Update",msg)
else:
    print("No new Android TV version")
