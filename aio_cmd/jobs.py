"""aio jobs [#|-r] - List/attach active sessions"""
import sys, os, subprocess as sp, re
from datetime import datetime
from . _common import init_db, load_cfg, is_active, tm

def run():
    init_db(); cfg = load_cfg(); sel = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] not in ('-r', '--running') else None
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees"))
    running = '-r' in sys.argv or '--running' in sys.argv
    r = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True); jbp = {}
    for s in (r.stdout.strip().split('\n') if r.returncode == 0 else []):
        if s and (pr := sp.run(['tmux', 'display-message', '-p', '-t', s, '#{pane_current_path}'], capture_output=True, text=True)).returncode == 0: jbp.setdefault(pr.stdout.strip(), []).append(s)
    for wp in [os.path.join(WT_DIR, d) for d in (os.listdir(WT_DIR) if os.path.exists(WT_DIR) else []) if os.path.isdir(os.path.join(WT_DIR, d))]:
        if wp not in jbp: jbp[wp] = []
    if not jbp: print("No jobs"); return
    jobs = []
    for jp, ss in list(jbp.items()):
        if not os.path.exists(jp): [sp.run(['tmux', 'kill-session', '-t', s], capture_output=True) for s in ss]; continue
        active = any(is_active(s) for s in ss) if ss else False
        if running and not active: continue
        m = re.search(r'-(\d{8})-(\d{6})-', os.path.basename(jp)); ct = datetime.strptime(f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S") if m else None
        td = (datetime.now() - ct).total_seconds() if ct else 0; ctd = f"{int(td/60)}m" if td < 3600 else f"{int(td/3600)}h" if td < 86400 else f"{int(td/86400)}d" if ct else ""
        jobs.append({'p': jp, 'n': os.path.basename(jp), 's': ss, 'wt': jp.startswith(WT_DIR), 'a': active, 'ct': ct, 'ctd': ctd})
    jobs = sorted(jobs, key=lambda x: x['ct'] or datetime.min)
    if sel and sel.isdigit() and (i := int(sel)) < len(jobs) and jobs[i]['s']: tm.go(jobs[i]['s'][0])
    for i, j in enumerate(jobs):
        st = '●' if j['a'] else '○'; ctd = f" {j['ctd']}" if j['ctd'] else ''
        print(f"  {i}  {st} {j['n'][:40]}{ctd}")
    print("\nSelect:\n  aio jobs 0")
