"""aio revert - Revert to commit"""
import os
from . _common import _git, _die

def run():
    cwd = os.getcwd()
    _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("x Not a git repo")
    logs = _git(cwd, 'log', '--format=%h %ad %s', '--date=format:%m/%d %H:%M', '-15').stdout.strip().split('\n')
    for i, l in enumerate(logs): print(f"  {i}. {l}")
    if not (c := input("\nRevert to #/q: ").strip()) or c == 'q': return
    if not c.isdigit() or int(c) >= len(logs): _die("x Invalid")
    h = logs[int(c)].split()[0]
    r = _git(cwd, 'revert', '--no-commit', f'{h}..HEAD')
    _git(cwd, 'commit', '-m', f'revert to {h}') if r.returncode == 0 else None
    if r.returncode != 0: _die(f"x Failed: {r.stderr.strip()}")
    print(f"✓ Reverted to {h}")
    if input("Push to main? (y/n): ").strip().lower() in ['y', 'yes']: _git(cwd, 'push'); print("✓ Pushed")
