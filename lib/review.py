"""a review - PRs + worktree cleanup"""
import subprocess as sp, json, os

def run():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wtdir = os.path.join(root, 'adata', 'worktrees')
    prs = sp.run(['gh','search','prs','--author','@me','--state','open',
        '--json','repository,number,title,headRefName,url'],capture_output=True,text=True).stdout
    items = json.loads(prs) if prs.strip() else []
    wts = set(os.listdir(wtdir)) if os.path.isdir(wtdir) else set()
    for p in items:
        b = p.get('headRefName',''); p['wt'] = b[3:] if b.startswith('wt-') and b[3:] in wts else ''
    if not items: print("  (no open PRs)"); return
    for i,p in enumerate(items):
        wt = f" [{p['wt']}]" if p['wt'] else ""
        print(f"  {i}. {p['repository']['nameWithOwner']}#{p['number']} {p['title']}{wt}")
    c = input("\n# or q> ").strip()
    if not c or c=='q' or not c[0].isdigit(): return
    p = items[int(c.split()[0])]; repo,num = p['repository']['nameWithOwner'],str(p['number'])
    if p['wt']: sp.run(f"cd '{wtdir}/{p['wt']}'&&a diff main",shell=True)
    else: sp.run(f'D=/tmp/pr-{num};rm -rf $D&&gh repo clone {repo} $D>/dev/null 2>&1&&cd $D&&gh pr checkout {num}>/dev/null 2>&1&&a diff main',shell=True)
    act = input("\n[m]erge [c]lose [o]pen [q]uit > ").strip().lower()
    if act=='m':
        sp.run(['gh','pr','merge','--repo',repo,num,'--squash','--delete-branch'])
        _clean(root,wtdir,p)
    elif act=='c':
        sp.run(['gh','pr','close','--repo',repo,num,'--delete-branch'])
        _clean(root,wtdir,p)
    elif act=='o':
        sp.run(['tmux','new-window','-c',f"{wtdir}/{p['wt']}" if p['wt'] else f"/tmp/pr-{num}"],capture_output=True)

def _clean(root,wtdir,p):
    if not p.get('wt'): return
    wp = os.path.join(wtdir,p['wt'])
    sp.run(['git','-C',root,'worktree','remove','--force',wp],capture_output=True)
    if os.path.isdir(wp): sp.run(['rm','-rf',wp])
    print(f"\u2713 cleaned {p['wt']}")

run()
