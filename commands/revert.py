"""aio revert - revert to previous commit"""
import subprocess as sp, os, sys

def _git(path, *a, **k):
    return sp.run(['git', '-C', path] + list(a), capture_output=True, text=True, **k)

def _die(m, c=1): print(f"x {m}"); sys.exit(c)

def run(args):
    cwd = os.getcwd()
    _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("Not a git repo")
    logs = _git(cwd, 'log', '--format=%h %ad %s', '--date=format:%m/%d %H:%M', '-15').stdout.strip().split('\n')
    for i, l in enumerate(logs): print(f"  {i}. {l}")
    c = input("\nRevert to #: ").strip()
    if not c.isdigit() or int(c) >= len(logs): _die("Invalid")
    h = logs[int(c)].split()[0]
    r = _git(cwd, 'revert', '--no-commit', f'{h}..HEAD')
    _git(cwd, 'commit', '-m', f'revert to {h}') if r.returncode == 0 else None
    print(f"✓ Reverted to {h}") if r.returncode == 0 else _die(f"Failed: {r.stderr.strip()}")
