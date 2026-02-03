"""a-sync folder backup:
  local only:  backup/<repo>/  (pre-sync snapshot)
  git+github:  common ssh login hub notes workspace docs tasks
  cloud only:  logs (a log sync → gdrive tar.zst, too large for git)
All git repos should use main branch."""
import os, subprocess as sp
from pathlib import Path
from ._common import SYNC_ROOT, RCLONE_REMOTES, RCLONE_BACKUP_PATH, DEVICE_ID, get_rclone
REPOS = {k: f'a-{k}' for k in 'common ssh login hub notes workspace docs tasks'.split()}

def _merge_rclone():
    import re;lc,rc=SYNC_ROOT/'login'/'rclone.conf',Path.home()/'.config/rclone/rclone.conf'
    if not lc.exists():return
    rc.parent.mkdir(parents=True,exist_ok=True);lt,rt=lc.read_text(),rc.read_text()if rc.exists()else''
    for n in'a-gdrive','a-gdrive2':
        if f'[{n}]'not in rt and(m:=re.search(rf'\[{n}\][^\[]*',lt)):rc.write_text(rt+m.group()+'\n');rt=rc.read_text()

def cloud_sync(local_path, name):
    rc = get_rclone();_merge_rclone()
    if not rc: return False, "no rclone"
    tar = f'{os.getenv("TMPDIR","/tmp")}/{name}-{DEVICE_ID}.tar.zst'
    if sp.run(f'tar -cf - -C {local_path} . 2>/dev/null | zstd -q > {tar}', shell=True).returncode>1: return False, "tar failed"
    ok = [r for r in RCLONE_REMOTES if sp.run([rc,'copyto',tar,f'{r}:{RCLONE_BACKUP_PATH}/{name}/{DEVICE_ID}.tar.zst','-q']).returncode==0]
    Path(tar).unlink(missing_ok=True)
    return bool(ok),f"{'✓'*len(ok)or'x'} {','.join(ok)or'fail'}"

def _sync_repo(path, repo_name, msg='sync'):
    path.parent.mkdir(parents=True,exist_ok=True);g=f'cd {path}&&';b=SYNC_ROOT/'backup'/path.name;path.exists()and sp.run(f'mkdir -p {b.parent}&&rm -rf {b}&&cp -r {path} {b}',shell=True,capture_output=True)
    if not sp.run(f'git -C {path} remote get-url origin',shell=True,capture_output=True).returncode:
        br=sp.run(f'git -C {path} branch --show-current',shell=True,capture_output=True,text=True).stdout.strip()or'main'
        sp.run(f'{g}git add -A&&git commit -qm "{msg}"',shell=True,capture_output=True)
        r=sp.run(f'{g}git pull -q --no-rebase origin {br};git push -q',shell=True,capture_output=True,text=True)
    else:
        r=sp.run(f'rm -rf {path};gh repo clone {repo_name} {path}||(mkdir -p {path}&&{g}git init -q&&echo "# {repo_name}">README.md&&git add -A&&git commit -qm init&&gh repo create {repo_name} --private --source=. --push)',shell=True,capture_output=True)
    url=sp.run(['git','-C',str(path),'remote','get-url','origin'],capture_output=True,text=True).stdout.strip()or'sync'
    if r.returncode:
        err=(r.stderr or r.stdout or '').strip().split('\n')[-1]
        print(f"x [{repo_name}] {err}\n  repo: {path}\n  backup: {b}\n  hint: use 'a c' and copy message for help debugging sync issue")
    return url

def sync(repo='common', msg='sync'): return _sync_repo(SYNC_ROOT/repo, REPOS.get(repo, f'a-{repo}'), msg)

HELP = """a sync - Sync a-sync repos to GitHub
  a sync       Sync all repos locally → GitHub
  a sync all   Sync local + broadcast to all SSH hosts
  a sync help  Show this help"""

def run():
    import sys
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if arg in ('help', '-h', '--help'): print(HELP); return
    os.system('pgrep -x inotifywait>/dev/null')and os.system(f'inotifywait -mqr --exclude \\.git -e close_write {SYNC_ROOT}|while read x;do a sync&done&')
    print(SYNC_ROOT)
    for repo, name in REPOS.items():
        path = SYNC_ROOT/repo; url = _sync_repo(path, name)
        t = sp.run(['git','-C',str(path),'log','-1','--format=%cd %s','--date=format:%Y-%m-%d %I:%M:%S %p'],capture_output=True,text=True).stdout.strip()
        print(f"\n[{repo}] {url}\nLast: {t}")
    if arg == 'all': print("\n--- Broadcasting to SSH hosts ---"); sp.run('a ssh all "a sync"', shell=True)
