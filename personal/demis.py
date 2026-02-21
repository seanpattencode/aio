#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'-p','Search for any Demis Hassabis interviews published today or yesterday. Reply ONLY: <found>YES or NO</found><title>title if found else NONE</title><url>url if found else NONE</url>'],capture_output=True,text=True,timeout=120)
f,t,u=re.search(r'<found>(\w+)</found>',r.stdout),re.search(r'<title>([^<]+)</title>',r.stdout),re.search(r'<url>([^<]+)</url>',r.stdout)
if f and f[1].upper()=='YES' and t and u and t[1]!='NONE':
    msg=f"New Demis Interview!\n\n{t[1]}\n{u[1]}"
    print(msg)
    save("g-demis",msg)
    if "--send" in sys.argv: send("Demis Hassabis Interview",msg)
else:
    print("No new Demis interviews")
