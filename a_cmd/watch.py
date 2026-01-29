"""aio watch - Watch session for prompts"""
import sys, time, re, subprocess as sp
from . _common import _die

def run():
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    wda or _die("Usage: a watch <session> [duration]")
    dur = int(sys.argv[3]) if len(sys.argv) > 3 else None
    print(f"Watching '{wda}'" + (f" for {dur}s" if dur else " (once)"))
    patterns = {re.compile(p): r for p, r in [(r'Are you sure\?', 'y'), (r'Continue\?', 'yes'), (r'\[y/N\]', 'y'), (r'\[Y/n\]', 'y')]}
    last, start = "", time.time()
    while True:
        if dur and (time.time() - start) > dur: break
        r = sp.run(['tmux', 'capture-pane', '-t', wda, '-p'], capture_output=True, text=True)
        if r.returncode != 0: print(f"x Session {wda} not found"); sys.exit(1)
        if r.stdout != last:
            for p, resp in patterns.items():
                if p.search(r.stdout): sp.run(['tmux', 'send-keys', '-t', wda, resp, 'Enter']); print(f"✓ Auto-responded"); break
            last = r.stdout
        time.sleep(0.1)
