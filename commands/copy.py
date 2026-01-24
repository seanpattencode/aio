"""aio copy - copy last command output to clipboard"""
import subprocess as sp, os, sys, shutil

def _clip():
    if os.environ.get('TERMUX_VERSION'): return 'termux-clipboard-set'
    if sys.platform == 'darwin': return 'pbcopy'
    for c in ['wl-copy', 'xclip -selection clipboard -i', 'xsel --clipboard --input']:
        if shutil.which(c.split()[0]): return c
    return None

def run(args):
    L = os.popen('tmux capture-pane -pJ -S -99').read().split('\n') if os.environ.get('TMUX') else []
    P = [i for i, l in enumerate(L) if '$' in l and '@' in l]
    u = next((i for i in reversed(P) if 'copy' in L[i]), len(L))
    p = next((i for i in reversed(P) if i < u), -1)
    full = '\n'.join(L[p+1:u]).strip() if P else ''
    clip = _clip()
    if clip:
        sp.run(clip, shell=True, input=full, text=True)
        s = full.replace('\n', ' ')
        print(f"✓ {s[:23]+'...'+s[-24:] if len(s)>50 else s}")
    else:
        print("x No clipboard tool found")
