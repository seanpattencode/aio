#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'-p','Search GitHub for most popular AI agent managers/frameworks. Reply ONLY:\n<top1>name:stars:1-line desc</top1>\n<top2>name:stars:1-line desc</top2>\n<top3>name:stars:1-line desc</top3>\n<trend>10 words on trends</trend>'],capture_output=True,text=True,timeout=120)
t1,t2,t3,tr=re.search(r'<top1>([^<]+)</top1>',r.stdout),re.search(r'<top2>([^<]+)</top2>',r.stdout),re.search(r'<top3>([^<]+)</top3>',r.stdout),re.search(r'<trend>([^<]+)</trend>',r.stdout)
rpt=f"1. {t1[1]}\n2. {t2[1]}\n3. {t3[1]}\n\nTrend: {tr[1].strip()}" if t1 and t2 and t3 and tr else r.stdout.strip()
out=f"AI Agent Managers:\n{rpt}"
print(out)
save("g-managers",out)
if "--send" in sys.argv: send("AI Agent Managers Report",rpt)
