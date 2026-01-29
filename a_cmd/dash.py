"""aio dash - Dashboard"""
import os, subprocess as sp
from . _common import init_db, tm

def run():
    init_db()
    wd = os.getcwd()
    if not tm.has('dash'):
        sp.run(['tmux', 'new-session', '-d', '-s', 'dash', '-c', wd])
        sp.run(['tmux', 'split-window', '-h', '-t', 'dash', '-c', wd, 'sh -c "aio jobs; exec $SHELL"'])
    os.execvp('tmux', ['tmux', 'switch-client' if 'TMUX' in os.environ else 'attach', '-t', 'dash'])
