#!/usr/bin/env python3
"""a agent run frontier          — scan for new frontier models
   a agent run frontier --send   — digest + email new finds"""
import re,sys,os
from pathlib import Path
from base import send, save, ask_gemini

D=Path(os.path.dirname(os.path.realpath(__file__)),'..','adata','git','rss')
KNOWN=D/'frontier.known'
LOG=D/'frontier.log'

def load_known():
    return set(KNOWN.read_text().splitlines()) if KNOWN.exists() else set()

def scan():
    r=ask_gemini('List current frontier AI models with API model IDs. '
        'Reply ONLY lines of: model_id company description\n'
        'e.g. gpt-4o OpenAI Multimodal flagship\nList 15.',timeout=300)
    items=[]
    for line in r.strip().splitlines():
        parts=line.split(None,2)
        if len(parts)>=2 and '-' in parts[0]: items.append((parts[0].lower(),parts[1],parts[2] if len(parts)>2 else ''))
    return items

if '--send' in sys.argv:
    if not LOG.exists() or not LOG.stat().st_size:
        print("No new frontier models accumulated"); sys.exit(0)
    arts=LOG.read_text(); LOG.write_text('')
    n=len([l for l in arts.splitlines() if l.strip()])
    print(arts); save("g-frontier",arts); send(f"New Frontier Models ({n})",arts)
else:
    D.mkdir(parents=True,exist_ok=True)
    known=load_known()
    new=[(mid,co,desc) for mid,co,desc in scan() if mid not in known]
    if not new: print("No new models"); sys.exit(0)
    with open(KNOWN,'a') as f:
        for mid,_,_ in new: f.write(mid+'\n')
    with open(LOG,'a') as f:
        for mid,co,desc in new: f.write(f"* {mid} ({co}) — {desc}\n")
    print(f"{len(new)} new models found")
