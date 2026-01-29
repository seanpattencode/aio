"""aio e - Open nvim"""
import os
from . _common import init_db, load_cfg, create_sess

def run():
    init_db()
    cfg = load_cfg()
    if 'TMUX' in os.environ:
        os.execvp('nvim', ['nvim', '.'])
    else:
        create_sess('edit', os.getcwd(), 'nvim .', cfg)
        os.execvp('tmux', ['tmux', 'attach', '-t', 'edit'])
