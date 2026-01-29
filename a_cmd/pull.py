"""aio pull - Sync with remote"""
import sys, os
from . _common import _git, _env, _die

def run():
    cwd = os.getcwd()
    _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("x Not a git repo")
    env = _env(); _git(cwd, 'fetch', 'origin', env=env)
    ref = 'origin/main' if _git(cwd, 'rev-parse', '--verify', 'origin/main').returncode == 0 else 'origin/master'
    info = _git(cwd, 'log', '-1', '--format=%h %s', ref).stdout.strip()
    print(f"! DELETE local changes -> {info}")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").strip().lower() in ['y', 'yes']) or _die("x Cancelled")
    _git(cwd, 'reset', '--hard', ref); _git(cwd, 'clean', '-f', '-d'); print(f"✓ Synced: {info}")
