#!/usr/bin/env python3
"""Generic Google News RSS scanner. Tracks seen in txt, accumulates new to .log.
Usage: rss.py <topic> [--name NAME]         scan + accumulate
       rss.py --digest <name> [--send]      emit + clear accumulated"""
import urllib.request,xml.etree.ElementTree as ET,html,re,os,sys
from pathlib import Path

D=Path(os.path.dirname(os.path.realpath(__file__)),'..','adata','git','rss')

def scan(topic,n=10):
    q=__import__('urllib.parse',fromlist=['quote_plus']).quote_plus(topic)
    xml=urllib.request.urlopen(urllib.request.Request(
        f'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en',
        headers={'User-Agent':'Mozilla/5.0'}),timeout=15).read()
    return [(i.findtext('title',''),i.findtext('link',''),
             html.unescape(re.sub('<[^>]+>',' ',i.findtext('description',''))).strip(),
             i.findtext('pubDate','')) for i in ET.fromstring(xml).findall('.//item')[:n]]

def _name(topic): return re.sub(r'\W+','-',topic.lower()).strip('-')

def accumulate(topic,name=None,n=10):
    """Scan RSS, append unseen articles to .log, mark seen. Returns count added."""
    name=name or _name(topic); D.mkdir(parents=True,exist_ok=True)
    sf=D/f'{name}.seen'
    seen=set(sf.read_text().splitlines()) if sf.exists() else set()
    new=[(t,l,d,p) for t,l,d,p in scan(topic,n) if l not in seen]
    if not new: return name,0
    with open(sf,'a') as f:
        for _,l,_2,_3 in new: f.write(l+'\n')
    with open(D/f'{name}.log','a') as f:
        for t,l,d,p in new: f.write(f'{t}\t{p}\t{l}\n')
    return name,len(new)

def digest(name):
    """Read accumulated .log, return articles, clear log."""
    lf=D/f'{name}.log'
    if not lf.exists() or not lf.stat().st_size: return []
    arts=[]
    for line in lf.read_text().splitlines():
        parts=line.split('\t',2)
        if len(parts)==3: arts.append(parts)
    lf.write_text('')
    return arts

if __name__=='__main__':
    if '--digest' in sys.argv:
        name=sys.argv[sys.argv.index('--digest')+1]
        arts=digest(name)
        if not arts: print(f"No accumulated articles for '{name}'"); sys.exit(0)
        out=f"{len(arts)} articles:\n\n"
        for t,p,l in arts: out+=f"* {t}\n  {p}\n\n"
        print(out)
        if '--send' in sys.argv:
            from base import send
            send(f"News digest: {name} ({len(arts)})",out)
    else:
        if len(sys.argv)<2: print("Usage: rss.py <topic> | rss.py --digest <name> [--send]"); sys.exit(1)
        name=sys.argv[sys.argv.index('--name')+1] if '--name' in sys.argv else None
        name,n=accumulate(sys.argv[1],name)
        print(f"{n} new articles accumulated for '{name}'" if n else f"No new articles for '{name}'")
