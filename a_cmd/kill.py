"""aio kill [#|all] - Kill tmux session(s)"""
import sys, subprocess as sp
from . _common import tm

def run():
    sel = sys.argv[2] if len(sys.argv) > 2 else None
    # Kill-all first, before any tmux calls that could hang
    if sel == 'all' or sys.argv[1] == 'killall': sp.run(['pkill', '-9', '-f', 'tmux']); sp.run(['clear']); print("✓"); return
    r = tm.ls(); sl = [s for s in r.stdout.strip().split('\n') if s and r.returncode == 0]
    if not sl: print("No sessions"); return
    if sel and sel.isdigit() and (i := int(sel)) < len(sl): sp.run(['tmux', 'kill-session', '-t', sl[i]]); print(f"✓ {sl[i]}"); return
    for i, s in enumerate(sl): print(f"  {i}  {s}")
    print("\nSelect:\n  a kill 0\n  a kill all")
