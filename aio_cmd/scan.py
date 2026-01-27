"""aio scan - Scan/clone repos. Usage: aio scan [gh] [name|#|#-#|all]"""
import sys, os, subprocess as sp, json
from pathlib import Path
from . _common import init_db, load_proj, add_proj, auto_backup

def run():
    init_db(); args = sys.argv[2:]; gh = 'gh' in args; args = [a for a in args if a!='gh']
    sel = next((a for a in args if a.isdigit() or a == 'all' or (a.replace('-','').isdigit() and '-' in a)), None)
    name = next((a for a in args if a not in (sel,) and not a.startswith('-') and not a.startswith('/') and not a.startswith('~')), None)

    if gh or name:
        r = sp.run(['gh', 'repo', 'list', '-L', '100', '--json', 'name,url,pushedAt'], capture_output=True, text=True)
        repos = sorted(json.loads(r.stdout or '[]'), key=lambda x: x.get('pushedAt',''), reverse=True)
        cloned = {os.path.basename(p) for p in load_proj()}

        # Name match or search filter
        if name:
            match = next((r for r in repos if r['name']==name), None)
            if match and name not in cloned: dest=os.path.expanduser(f'~/projects/{name}'); os.makedirs(os.path.dirname(dest),exist_ok=True); r=sp.run(['gh','repo','clone',match['url'],dest],capture_output=True,text=True); ok,_=add_proj(dest) if r.returncode==0 or os.path.isdir(dest) else (False,''); print(f"{'✓' if ok else 'x'} {name}"); auto_backup() if ok else None; return
            elif name in cloned: print(f"○ {name} already added"); return
        repos = [(r['name'],r['url'],r.get('pushedAt','')[:10]) for r in repos if r['name'] not in cloned and (not name or name.lower() in r['name'].lower())]
        if not repos: print("No new GitHub repos"); return
        pg=0
        while True:
            for i,(n,u,d) in enumerate(repos[pg*10:(pg+1)*10],pg*10): print(f"  {i}. {n:<25} {d}")
            more=pg*10+10<len(repos); print(f"  [{len(repos)} repos] /search m=more" if more else f"  [{len(repos)} repos] /search")
            if not sel: sel=input("\nClone (#,#-#,all,q): ").strip()if sys.stdin.isatty()else None
            if sel=='m'and more: pg+=1; sel=None; continue
            if sel and sel[0]=='/': repos=[(n,u,d)for n,u,d in repos if sel[1:].lower()in n.lower()]; pg=0; sel=None; continue
            break
        if not sel or sel=='q': return
        idxs = list(range(len(repos))) if sel == 'all' else [j for x in sel.replace(',', ' ').split() for j in (range(int(x.split('-')[0]), int(x.split('-')[1])+1) if '-' in x else [int(x)]) if 0 <= j < len(repos)]
        pd = os.path.expanduser('~/projects'); os.makedirs(pd, exist_ok=True)
        for i in idxs: n, u, _ = repos[i]; dest = f"{pd}/{n}"; r = sp.run(['gh', 'repo', 'clone', u, dest], capture_output=True, text=True); ok, _ = add_proj(dest) if r.returncode == 0 or os.path.isdir(dest) else (False, ''); print(f"{'✓' if ok else 'x'} {n}")
        auto_backup() if idxs else None
    else:
        d = os.path.expanduser(next((a for a in args if a not in (sel,)), '~/projects'))
        existing = set(load_proj())
        repos = sorted([p.parent for p in Path(d).rglob('.git') if p.exists() and str(p.parent) not in existing and '/.' not in str(p.parent)], key=lambda x: x.name.lower())[:50]
        if not repos: print(f"No new repos in {d}"); return
        pg=0
        while True:
            for i,r in enumerate(repos[pg*10:(pg+1)*10],pg*10): print(f"  {i}. {r.name:<25} {str(r)}")
            more=pg*10+10<len(repos); print(f"  [{len(repos)} repos] gh=GitHub m=more" if more else f"  [{len(repos)} repos] gh=GitHub")
            if not sel: sel=input("\nAdd (#,#-#,all,gh,q): ").strip()if sys.stdin.isatty()else None
            if sel=='m'and more: pg+=1; sel=None; continue
            if sel=='gh': sys.argv.insert(2,'gh'); return run()
            break
        if not sel or sel=='q': return
        idxs = list(range(len(repos)))if sel=='all'else[j for x in sel.replace(',',' ').split()for j in(range(int(x.split('-')[0]),int(x.split('-')[1])+1)if'-'in x else[int(x)])if 0<=j<len(repos)]
        for i in idxs: ok, _ = add_proj(str(repos[i])); print(f"{'✓' if ok else 'x'} {repos[i].name}")
        auto_backup() if idxs else None
