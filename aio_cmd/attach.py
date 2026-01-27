"""aio attach [#] - Reconnect to session"""
import sys, os
from . _common import init_db, load_cfg, db, tm

def run():
    init_db(); cfg = load_cfg(); sel = sys.argv[2] if len(sys.argv) > 2 else None
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees")); cwd = os.getcwd()
    if WT_DIR in cwd and (p := cwd.replace(WT_DIR + '/', '').split('/')) and len(p) >= 2 and tm.has(s := f"{p[0]}-{p[1]}"): tm.go(s)
    with db() as c: runs = c.execute("SELECT id, repo FROM multi_runs ORDER BY created_at DESC LIMIT 10").fetchall()
    if not runs: print("No sessions"); return
    if sel and sel.isdigit() and (i := int(sel)) < len(runs): tm.go(f"{os.path.basename(runs[i][1])}-{runs[i][0]}")
    for i, (rid, repo) in enumerate(runs): print(f"  {i}  {'●' if tm.has(f'{os.path.basename(repo)}-{rid}') else '○'} {os.path.basename(repo)}-{rid}")
    print("\nSelect:\n  aio attach 0")
