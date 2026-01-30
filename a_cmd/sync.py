"""aio sync - Git-based sync to GitHub
RFC 5322 with .txt is the default and preferred way to format data, because it doesn't hide information, doesn't break, and yet is machine searchable with metadata.
This allows for isolation, so a sync conflict in notes doesn't bottleneck agent work logging."""
import os, subprocess as sp
from pathlib import Path
from ._common import SCRIPT_DIR

SYNC_ROOT = Path(SCRIPT_DIR).parent / 'a-sync'
REPOS = {'common': 'aio-common', 'ssh': 'aio-ssh', 'logs': 'aio-logs'}

def _sync_repo(path, repo_name, msg='sync', bg=True):
    path.mkdir(parents=True, exist_ok=True); cmd='cd {}; git init -q; git add -A; git commit -qm "{}" 2>/dev/null; git remote get-url origin || gh repo create {} --private --source . --push -y; git pull --rebase -q 2>/dev/null; git push -q'.format(path, msg, repo_name)
    (sp.Popen if bg else sp.run)(cmd, shell=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL); return sp.run(['git','-C',str(path),'remote','get-url','origin'], capture_output=True, text=True).stdout.strip() or 'syncing...'

def sync(repo='common', msg='sync', bg=True):
    return _sync_repo(SYNC_ROOT/repo, REPOS.get(repo, f'aio-{repo}'), msg, bg)

def sync_all(msg='sync', bg=False):
    return {r: _sync_repo(SYNC_ROOT/r, name, msg, bg) for r, name in REPOS.items()}

def run():
    print(f"{SYNC_ROOT}")
    for repo, name in REPOS.items():
        path = SYNC_ROOT/repo; url = _sync_repo(path, name, bg=False)
        t = sp.run(['git','-C',str(path),'log','-1','--format=%cd %s','--date=format:%Y-%m-%d %I:%M:%S %p'],capture_output=True,text=True).stdout.strip()
        files = [f for f in sp.run(['git','-C',str(path),'ls-files'],capture_output=True,text=True).stdout.split() if f]
        print(f"\n[{repo}] {url}\nLast: {t}"); [print(f"  {f}") for f in files]
