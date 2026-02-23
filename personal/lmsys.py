#!/usr/bin/env python3
"""a agent run lmsys          — scan leaderboards, detect changes
   a agent run lmsys --send   — digest + email changes"""
import urllib.request,json,sys,os
from pathlib import Path
from base import send, save

D=Path(os.path.dirname(os.path.realpath(__file__)),'..','adata','git','rss')
KNOWN=D/'lmsys.known'
LOG=D/'lmsys.log'
URL='https://raw.githubusercontent.com/lmarena/arena-catalog/main/data/leaderboard-text.json'
CATS={'full':'Text Overall','coding':'Coding','industry_software_and_it_services':'Software/IT'}

def fetch():
    r=urllib.request.urlopen(urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0'}),timeout=30)
    return json.loads(r.read())

def load_known():
    if not KNOWN.exists(): return {}
    return json.loads(KNOWN.read_text())

def save_known(d):
    D.mkdir(parents=True,exist_ok=True)
    KNOWN.write_text(json.dumps(d))

def scan():
    data=fetch()
    known=load_known()
    alerts=[]
    cur={}
    for cat,label in CATS.items():
        if cat not in data: continue
        top=sorted(data[cat].items(),key=lambda x:-x[1]['rating'])[:10]
        cur[cat]={'top10':[n for n,_ in top],'num1':top[0][0],'scores':{n:round(v['rating'],1) for n,v in top}}
        prev=known.get(cat)
        if not prev:
            alerts.append(f"[{label}] Initial top 10:\n"+'\n'.join(f"  #{i+1} {n} ({cur[cat]['scores'][n]})" for i,n in enumerate(cur[cat]['top10'])))
            continue
        if cur[cat]['num1']!=prev['num1']:
            alerts.append(f"[{label}] NEW #1: {cur[cat]['num1']} ({cur[cat]['scores'][cur[cat]['num1']]}) — was {prev['num1']}")
        new_top10=set(cur[cat]['top10'])-set(prev['top10'])
        for n in new_top10:
            idx=cur[cat]['top10'].index(n)+1
            alerts.append(f"[{label}] New top 10 entry: #{idx} {n} ({cur[cat]['scores'][n]})")
        dropped=set(prev['top10'])-set(cur[cat]['top10'])
        for n in dropped:
            alerts.append(f"[{label}] Dropped from top 10: {n}")
    return cur,alerts

if '--send' in sys.argv:
    if not LOG.exists() or not LOG.stat().st_size:
        print("No leaderboard changes accumulated"); sys.exit(0)
    arts=LOG.read_text(); LOG.write_text('')
    n=len([l for l in arts.splitlines() if l.startswith('[')])
    print(arts); save("g-lmsys",arts); send(f"LMSYS Leaderboard Changes ({n})",arts)
else:
    D.mkdir(parents=True,exist_ok=True)
    cur,alerts=scan()
    save_known(cur)
    if not alerts: print("No leaderboard changes"); sys.exit(0)
    out='\n'.join(alerts)
    print(out)
    with open(LOG,'a') as f: f.write(out+'\n')
