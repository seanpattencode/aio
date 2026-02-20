"""aio w* - Worktree commands"""
import sys, os
from _common import init_db, load_cfg, load_proj, wt_list, wt_find, wt_rm

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/a/adata/worktrees"))
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == 'w':
        wt_list(WT_DIR)
        sys.exit(0)

    wp = wt_find(WT_DIR, arg[1:].rstrip('-'))
    if arg.endswith('-'):
        wt_rm(wp, PROJ, confirm='--yes' not in sys.argv and '-y' not in sys.argv) if wp else print(f"x Not found")
        sys.exit(0)

    if wp:
        os.chdir(wp)
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])

    print(f"x Not found: {arg[1:]}")
    sys.exit(1)

run()
