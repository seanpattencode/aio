"""aio copy - Copy last command output"""
import os, subprocess as sp
from . _common import _clip

def run():
    L = os.popen('tmux capture-pane -pJ -S -99').read().split('\n') if os.environ.get('TMUX') else []
    P = [i for i, l in enumerate(L) if '$' in l and '@' in l]
    u = next((i for i in reversed(P) if 'copy' in L[i]), len(L))
    p = next((i for i in reversed(P) if i < u), -1)
    full = '\n'.join(L[p+1:u]).strip() if P else ''
    sp.run(_clip(), shell=True, input=full, text=True)
    s = full.replace('\n', ' ')
    print(f"✓ {s[:23]+'...'+s[-24:] if len(s) > 50 else s}")
