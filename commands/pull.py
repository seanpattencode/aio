"""aio pull - sync with remote"""
import subprocess as sp, os, sys

def _git(path, *a, **k):
    return sp.run(['git', '-C', path] + list(a), capture_output=True, text=True, **k)

def _die(m, c=1): print(f"x {m}"); sys.exit(c)

def _env():
    e = os.environ.copy(); e.pop('DISPLAY', None); e.pop('GPG_AGENT_INFO', None); e['GIT_TERMINAL_PROMPT'] = '0'; return e

def run(args):
    cwd = os.getcwd()
    _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("Not a git repo")
    env = _env(); _git(cwd, 'fetch', 'origin', env=env)
    ref = 'origin/main' if _git(cwd, 'rev-parse', '--verify', 'origin/main').returncode == 0 else 'origin/master'
    info = _git(cwd, 'log', '-1', '--format=%h %s', ref).stdout.strip()
    print(f"! DELETE local changes -> {info}")
    ('--yes' in args or '-y' in args or input("Continue? (y/n): ").strip().lower() in ['y', 'yes']) or _die("Cancelled")
    _git(cwd, 'reset', '--hard', ref); _git(cwd, 'clean', '-f', '-d')
    print(f"✓ Synced: {info}")
