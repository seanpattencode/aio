"""aio tree - Create worktree"""
import sys, os
from datetime import datetime
from . _common import init_db, load_cfg, load_proj, wt_create, _git, _die

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/aWorktrees"))
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    proj = PROJ[int(wda)] if wda and wda.isdigit() and int(wda) < len(PROJ) else os.getcwd()
    _git(proj, 'rev-parse', '--git-dir').returncode == 0 or _die("x Not a git repo")
    wp = wt_create(proj, datetime.now().strftime('%Y%m%d-%H%M%S'), WT_DIR)
    wp or sys.exit(1)
    os.chdir(wp); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
