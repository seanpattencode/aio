"""aio update - Update aio"""
import os, subprocess as sp, shutil
from . _common import _sg, list_all, init_db, SCRIPT_DIR, DATA_DIR

def _setup_sync():
    if not shutil.which('gh') or sp.run(['gh','auth','status'],capture_output=True).returncode!=0: return
    sp.run('hp=~/.local/bin/git-credential-gh;mkdir -p $(dirname $hp);echo "#!/bin/sh\nexec $(which gh) auth git-credential \\\"\\$@\\\"">$hp;chmod +x $hp;git config --global credential.helper $hp',shell=True,capture_output=True)
    if os.path.isdir(f"{DATA_DIR}/.git"): print("✓ Sync"); return
    url = sp.run(['gh','repo','view','aio-sync','--json','url','-q','.url'],capture_output=True,text=True).stdout.strip() or sp.run(['gh','repo','create','aio-sync','--private','-y'],capture_output=True,text=True).stdout.strip()
    url and sp.run(f'mkdir -p "{DATA_DIR}"&&cd "{DATA_DIR}"&&git init -b main -q;git remote add origin {url} 2>/dev/null;echo "*.db*\n*.log\nlogs/\n*cache*\ntiming.jsonl\nnotebook/\n.device">.gitignore;git fetch origin&&git reset --hard origin/main 2>/dev/null||(git add -A&&git -c user.name=aio -c user.email=a@a commit -m init -q&&git push -u origin main)',shell=True,capture_output=True) and print("✓ Sync")

def run():
    if _sg('rev-parse', '--git-dir').returncode != 0: print("x Not in git repo"); return
    print("Checking..."); before = _sg('rev-parse', 'HEAD').stdout.strip()[:8]
    if not before or _sg('fetch').returncode != 0: return
    _sh=f'bash {SCRIPT_DIR}/install.sh --shell>/dev/null'
    if 'behind' not in _sg('status', '-uno').stdout: print(f"✓ Up to date ({before})"); os.system(_sh); init_db(); list_all(); _setup_sync(); return
    print("Downloading..."); _sg('pull', '--ff-only'); after = _sg('rev-parse', 'HEAD').stdout.strip()[:8]; print(f"✓ {before} -> {after}" if after else "✓ Done")
    os.system(_sh); init_db(); list_all(); print("Run: source ~/.bashrc"); _setup_sync()
