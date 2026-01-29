"""aio sync - Git-based sync to GitHub"""
import os, subprocess as sp
DATA = os.path.expanduser('~/.local/share/a')

def sync(msg='sync'):
    os.makedirs(DATA, exist_ok=True); sp.Popen('cd {}; git init -q; git add -A; git commit -qm "{}"; git remote get-url origin || gh repo create aio-sync --private --source . --push -y; git push -q'.format(DATA, msg), shell=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL); return sp.run(['git','-C',DATA,'remote','get-url','origin'], capture_output=True, text=True).stdout.strip() or 'syncing...'

def run(): print(f"{DATA}\n{sync()}"); [print(f) for f in sorted(os.listdir(DATA)) if not f.startswith('.')]
