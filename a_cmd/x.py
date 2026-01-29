"""aio x - Kill all sessions"""
import subprocess as sp

def run():
    sp.run(['tmux', 'kill-server'])
    print("✓ All sessions killed")
