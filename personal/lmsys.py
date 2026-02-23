# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright"]
# ///
"""a agent run lmsys          — scan leaderboards, detect changes
   a agent run lmsys --send   — digest + email changes"""
import json,sys,os,subprocess
from pathlib import Path

D=Path(os.path.dirname(os.path.realpath(__file__)),'..','adata','git','rss')
sys.path.insert(0,str(Path(__file__).parent))
from base import send, save

KNOWN=D/'lmsys.known'
LOG=D/'lmsys.log'
BOARDS={'text':'Text Overall','code':'Coding'}

def ensure_browser():
    """Install chromium if missing"""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
    except:
        print("Installing chromium..."); subprocess.run([sys.executable,'-m','playwright','install','chromium'],check=True)

def fetch():
    from playwright.sync_api import sync_playwright
    ensure_browser()
    results={}
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True)
        pg=b.new_page()
        for board,label in BOARDS.items():
            url=f'https://lmarena.ai/leaderboard/{board}'
            pg.goto(url,timeout=30000)
            pg.wait_for_timeout(5000)
            for _ in range(3):
                rows=pg.evaluate('''() => {
                    let rows=[...document.querySelectorAll('table tbody tr')];
                    return rows.slice(0,30).map((r,i)=>{
                        let c=r.querySelectorAll('td');
                        return {rank:parseInt(c[0]?.textContent)||i+1, name:c[2]?.textContent?.trim()||'', score:c[3]?.textContent?.trim()||''};
                    }).filter(r=>r.name&&r.name.length>2);
                }''')
                if rows: break
                pg.wait_for_timeout(3000)
            results[board]={'label':label,'top':rows[:10]}
        b.close()
    return results

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
    for board,info in data.items():
        label=info['label']
        top=info['top']
        if not top: continue
        cur[board]={'top10':[r['name'] for r in top],'num1':top[0]['name'],'scores':{r['name']:r['score'] for r in top}}
        prev=known.get(board)
        if not prev:
            alerts.append(f"[{label}] Initial top 10:\n"+'\n'.join(f"  #{i+1} {r['name']} ({r['score']})" for i,r in enumerate(top)))
            continue
        if cur[board]['num1']!=prev['num1']:
            alerts.append(f"[{label}] NEW #1: {cur[board]['num1']} ({cur[board]['scores'][cur[board]['num1']]}) — was {prev['num1']}")
        new_top10=set(cur[board]['top10'])-set(prev['top10'])
        for n in new_top10:
            idx=cur[board]['top10'].index(n)+1
            alerts.append(f"[{label}] New top 10 entry: #{idx} {n} ({cur[board]['scores'].get(n,'')})")
        dropped=set(prev['top10'])-set(cur[board]['top10'])
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
