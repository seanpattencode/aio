"""aio cleanup - Clean worktrees and runs"""
import sys, os, shutil
from . _common import init_db, load_cfg, load_proj, db, _wt_items, _git, _die

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/aWorktrees"))
    wts = _wt_items(WT_DIR)
    with db() as c: cnt = c.execute("SELECT COUNT(*) FROM multi_runs").fetchone()[0]
    if not wts and not cnt: print("Nothing to clean"); sys.exit(0)
    print(f"Will delete: {len(wts)} dirs, {cnt} db entries")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").lower() in ['y', 'yes']) or _die("x")
    for wt in wts:
        try: shutil.rmtree(os.path.join(WT_DIR, wt)); print(f"✓ {wt}")
        except: pass
    [_git(p, 'worktree', 'prune') for p in PROJ if os.path.exists(p)]
    with db() as c: c.execute("DELETE FROM multi_runs"); c.commit()
    print("✓ Cleaned")
