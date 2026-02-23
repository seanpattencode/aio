#!/usr/bin/env python3
"""a agent run managers          — scan for new agent frameworks
   a agent run managers --send   — digest + email new finds"""
import re,sys,os
from pathlib import Path
from base import send, save, ask_gemini

D=Path(os.path.dirname(os.path.realpath(__file__)),'..','adata','git','rss')
KNOWN=D/'managers.known'
LOG=D/'managers.log'

def load_known():
    return set(KNOWN.read_text().splitlines()) if KNOWN.exists() else set()

def scan():
    r=ask_gemini('Search GitHub for AI agent managers, orchestrators, and frameworks. '
        'Find 15 including any new/emerging ones. Reply ONLY with lines of: github_url stars short_desc\n'
        'Example: https://github.com/langchain-ai/langchain 100k LLM app framework\n'
        'One per line, nothing else.',timeout=180)
    items=[]
    for line in r.strip().splitlines():
        m=re.match(r'(https://github\.com/[^\s]+)\s+(\S+)\s+(.*)',line)
        if m: items.append((m[1].rstrip('/').lower(),m[2],m[3].strip()))
    return items

if '--send' in sys.argv:
    if not LOG.exists() or not LOG.stat().st_size:
        print("No new agent frameworks accumulated"); sys.exit(0)
    arts=LOG.read_text(); LOG.write_text('')
    n=len([l for l in arts.splitlines() if l.strip()])
    print(arts); save("g-managers",arts); send(f"New Agent Frameworks ({n})",arts)
else:
    D.mkdir(parents=True,exist_ok=True)
    known=load_known()
    new=[(url,stars,desc) for url,stars,desc in scan() if url not in known]
    if not new: print("No new frameworks"); sys.exit(0)
    with open(KNOWN,'a') as f:
        for url,_,_ in new: f.write(url+'\n')
    with open(LOG,'a') as f:
        for url,stars,desc in new: f.write(f"* {url} ({stars}) — {desc}\n")
    print(f"{len(new)} new frameworks found")
