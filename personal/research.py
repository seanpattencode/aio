#!/usr/bin/env python3
"""Research agent managers vs aio - what features to steal/avoid"""
import subprocess,shutil,os,re,sys
from base import send, save, AIO

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')

# Read aio.py summary
aio_code=open(AIO).read()[:3000]

r=subprocess.run([gemini,'-p',f'''Compare aio (code below) to popular agent managers (AutoGPT, LangChain, CrewAI, MetaGPT).

aio.py:
{aio_code}

Reply ONLY:
<steal>3 features aio should steal from others</steal>
<avoid>2 things others do wrong that aio should avoid</avoid>
<unique>1 thing aio does better</unique>
<action>specific next feature to implement</action>'''],capture_output=True,text=True,timeout=300)

steal=re.search(r'<steal>([^<]+)</steal>',r.stdout)
avoid=re.search(r'<avoid>([^<]+)</avoid>',r.stdout)
unique=re.search(r'<unique>([^<]+)</unique>',r.stdout)
action=re.search(r'<action>([^<]+)</action>',r.stdout)

msg=f"Agent Manager Research\n\nSTEAL:\n{steal[1] if steal else '?'}\n\nAVOID:\n{avoid[1] if avoid else '?'}\n\nAIO UNIQUE:\n{unique[1] if unique else '?'}\n\nNEXT ACTION:\n{action[1] if action else '?'}"
print(msg)
save("g-research",msg)
if "--send" in sys.argv: send("Agent Manager Research",msg)
