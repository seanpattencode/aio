"""aio ls [#] - List tmux sessions, optionally attach by number"""
import sys, subprocess as sp
from . _common import tm

def run():
    r = tm.ls(); sl = [s for s in r.stdout.strip().split('\n') if s and r.returncode == 0]
    if not sl: print("No sessions"); return
    sel = sys.argv[2] if len(sys.argv) > 2 else None
    if sel and sel.isdigit() and (i := int(sel)) < len(sl): tm.go(sl[i])
    for i, s in enumerate(sl):
        p = sp.run(['tmux', 'display-message', '-p', '-t', s, '#{pane_current_path}'], capture_output=True, text=True)
        print(f"  {i}  {s}: {p.stdout.strip() if p.returncode == 0 else ''}")
    print("\nSelect:\n  aio ls 0")
