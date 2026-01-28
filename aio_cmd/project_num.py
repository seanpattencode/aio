"""aio <#> - Open project by number"""
import sys, os, subprocess as sp
from . _common import init_db, load_proj, load_apps, fmt_cmd, SCRIPT_DIR

_OK = os.path.expanduser('~/.local/share/aios/logs/push.ok')

def run():
    init_db(); PROJ = load_proj(); APPS = load_apps(); idx = int(sys.argv[1])
    if 0 <= idx < len(PROJ):
        p, repo = PROJ[idx]
        if not os.path.exists(p) and repo:
            p = os.path.expanduser(f"~/projects/{os.path.basename(p)}"); os.makedirs(os.path.dirname(p), exist_ok=True)
            print(f"Cloning {repo} -> {p}"); sp.run(['git','clone',repo,p]).returncode == 0 or sys.exit(1)
        print(f"Opening project {idx}: {p}")
        sp.Popen([sys.executable, os.path.join(SCRIPT_DIR, 'aio_new.py'), '_ghost', p], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        sp.Popen(f'git -C "{p}" ls-remote --exit-code origin HEAD &>/dev/null && touch "{_OK}"', shell=True)
        os.chdir(p)
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    elif 0 <= idx - len(PROJ) < len(APPS):
        an, ac = APPS[idx - len(PROJ)]
        print(f"> Running: {an}\n   Command: {fmt_cmd(ac)}")
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash'), '-c', ac])
    else:
        print(f"x Invalid index: {idx}")
        sys.exit(1)
