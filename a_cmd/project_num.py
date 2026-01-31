"""a <#> - Open project"""
import sys, os, subprocess as sp
from . _common import init_db, load_cfg, load_proj, load_apps, load_sess, resolve_cmd, fmt_cmd, SYNC_ROOT, _ghost_spawn

_OK = os.path.expanduser('~/.local/share/a/logs/push.ok')

def run():
    init_db(); PROJ = load_proj(); APPS = load_apps(); idx = int(sys.argv[1])
    if 0 <= idx < len(PROJ):
        p, repo = PROJ[idx]
        if not os.path.exists(p) and repo:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if sp.run(['gh','auth','token'], capture_output=True).returncode != 0:
                t = next((l.split(':',1)[1].strip() for f in sorted((SYNC_ROOT/'login').glob('gh_*.txt'), key=lambda f: -f.stat().st_mtime) for l in f.read_text().splitlines() if l.startswith('Token:')), None)
                t and sp.run(f'echo "{t}"|gh auth login --with-token', shell=True, capture_output=True) and print("✓ gh auth from sync")
            print(f"Cloning {repo}..."); sp.run(['git','clone',repo,p]).returncode and sys.exit(1)
        print(f"Opening project {idx}: {p}")
        sp.Popen(f'git -C "{p}" ls-remote --exit-code origin HEAD>/dev/null 2>&1&&touch "{_OK}"', shell=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        os.chdir(p); cfg=load_cfg(); _ghost_spawn(p,load_sess(cfg),cfg); os.execvp(sh:=os.environ.get('SHELL','/bin/bash'),[sh])
    elif 0 <= idx - len(PROJ) < len(APPS):
        an, ac = APPS[idx - len(PROJ)]; resolved = resolve_cmd(ac)
        print(f"> Running: {an}\n   Command: {fmt_cmd(resolved)}")
        os.execvp(sh:=os.environ.get('SHELL','/bin/bash'), [sh, '-c', resolved])
    else:
        print(f"x Invalid index: {idx}"); sys.exit(1)
