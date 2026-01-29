"""aio repo - Create dir and GitHub repo"""
import sys, os, subprocess as sp

def run():
    name = sys.argv[2] if len(sys.argv) > 2 else None
    if not name: print("Usage: a repo <name>"); sys.exit(1)
    os.makedirs(name, exist_ok=True); os.chdir(name)
    sp.run(['git', 'init', '-q'])
    sp.run(['gh', 'repo', 'create', name, '--public', '--source=.'])
