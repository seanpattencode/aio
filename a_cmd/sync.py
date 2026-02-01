"""aio sync - Git sync to GitHub, rclone sync to cloud
Per-device files are safe: each device writes its own, viewers can't corrupt.
Accidental edits on device B get overwritten by device A's next sync."""
import os, subprocess as sp
from pathlib import Path
from ._common import SYNC_ROOT, RCLONE_REMOTES, RCLONE_BACKUP_PATH, DEVICE_ID, get_rclone
REPOS = {k: f'a-{k}' for k in 'common ssh login hub notes workspace'.split()}

def _merge_rclone():
    import re;lc,rc=SYNC_ROOT/'login'/'rclone.conf',Path.home()/'.config/rclone/rclone.conf'
    if not lc.exists():return
    rc.parent.mkdir(parents=True,exist_ok=True);lt,rt=lc.read_text(),rc.read_text()if rc.exists()else''
    for n in('a-gdrive','a-gdrive2'):
        if f'[{n}]'not in rt and(s:=re.search(rf'\[{n}\][^\[]*',lt)):rc.write_text(rt+s.group()+'\n');rt=rc.read_text()

def cloud_sync(local_path, name):
    """Tar + upload to cloud. Returns (ok, msg)."""
    rc = get_rclone();_merge_rclone()
    if not rc: return False, "no rclone"
    tar = f'{os.getenv("TMPDIR","/tmp")}/{name}-{DEVICE_ID}.tar.zst'
    if sp.run(f'tar -cf - -C {local_path} . 2>/dev/null | zstd -q > {tar}', shell=True).returncode>1: return False, "tar failed"
    ok = [r for r in RCLONE_REMOTES if sp.run([rc,'copyto',tar,f'{r}:{RCLONE_BACKUP_PATH}/{name}/{DEVICE_ID}.tar.zst','-q']).returncode==0]
    Path(tar).unlink(missing_ok=True)
    return bool(ok),f"{'✓'*len(ok)or'x'} {','.join(ok)or'fail'}"

def _sync_repo(path, repo_name, msg='sync'):
    path.parent.mkdir(parents=True,exist_ok=True);g=f'cd {path}&&'
    if (path/'.git').exists():
        sp.run(f'{g}git rebase --abort;git merge --abort;git checkout -q main 2>/dev/null',shell=True,capture_output=True)
        sp.run(f'{g}git add -A&&git commit -qm "{msg}"',shell=True,capture_output=True)
        r=sp.run(f'{g}git pull -q&&git push -q',shell=True,capture_output=True,text=True)
    else:
        r=sp.run(f'gh repo clone {repo_name} {path} 2>/dev/null||(mkdir -p {path}&&{g}git init -q&&echo "# {repo_name}">README.md&&git add -A&&git commit -qm "init"&&gh repo create {repo_name} --private --source=. --push)',shell=True,capture_output=True,text=True)
    url=sp.run(['git','-C',str(path),'remote','get-url','origin'],capture_output=True,text=True).stdout.strip()or'sync'
    if r.returncode:print(f"x [{repo_name}]: {g}git status")
    return url

def sync(repo='common', msg='sync'): return _sync_repo(SYNC_ROOT/repo, REPOS.get(repo, f'a-{repo}'), msg)
def sync_all(msg='sync'): return {r: _sync_repo(SYNC_ROOT/r, name, msg) for r, name in REPOS.items()}

def run():
    print(f"{SYNC_ROOT}")
    for repo, name in REPOS.items():
        path = SYNC_ROOT/repo; url = _sync_repo(path, name)
        t = sp.run(['git','-C',str(path),'log','-1','--format=%cd %s','--date=format:%Y-%m-%d %I:%M:%S %p'],capture_output=True,text=True).stdout.strip()
        print(f"\n[{repo}] {url}\nLast: {t}")
