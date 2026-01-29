"""aio kill [#|all] - Kill tmux session(s)"""
import sys, subprocess as sp
from . _common import tm

def run():
    r = tm.ls(); sl = [s for s in r.stdout.strip().split('\n') if s and r.returncode == 0]
    if not sl: print("No sessions"); return
    sel = sys.argv[2] if len(sys.argv) > 2 else None
    if sel == 'all': sp.run(['tmux', 'kill-server']); print("✓"); return
    if sel and sel.isdigit() and (i := int(sel)) < len(sl): sp.run(['tmux', 'kill-session', '-t', sl[i]]); print(f"✓ {sl[i]}"); return
    for i, s in enumerate(sl): print(f"  {i}  {s}")
    print("\nSelect:\n  aio kill 0")
