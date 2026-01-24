"""aio push - commit and push"""
import subprocess as sp, os, sys, shutil
from pathlib import Path

def _git(path, *a, **k):
    return sp.run(['git', '-C', path] + list(a), capture_output=True, text=True, **k)

def _die(m, c=1): print(f"x {m}"); sys.exit(c)

def _env():
    e = os.environ.copy(); e.pop('DISPLAY', None); e.pop('GPG_AGENT_INFO', None); e['GIT_TERMINAL_PROMPT'] = '0'; return e

def _git_main(p):
    r = _git(p, 'symbolic-ref', 'refs/remotes/origin/HEAD')
    return r.stdout.strip().replace('refs/remotes/origin/', '') if r.returncode == 0 else ('main' if _git(p, 'rev-parse', '--verify', 'main').returncode == 0 else 'master')

def _git_push(p, b, env, force=False):
    r = _git(p, 'push', *(['--force'] if force else []), 'origin', b, env=env)
    if r.returncode == 0: print(f"✓ Pushed to {b}"); return True
    err = r.stderr.strip() or r.stdout.strip()
    if 'non-fast-forward' in err and input("! Force push? (y/n): ").lower() in ['y', 'yes']:
        _git(p, 'fetch', 'origin', env=env); return _git_push(p, b, env, True)
    print(f"x Push failed: {err}"); return False

def ensure_git_cfg():
    n, e = sp.run(['git', 'config', 'user.name'], capture_output=True, text=True), sp.run(['git', 'config', 'user.email'], capture_output=True, text=True)
    if n.returncode == 0 and e.returncode == 0 and n.stdout.strip() and e.stdout.strip(): return True
    if not shutil.which('gh'): return False
    try:
        r = sp.run(['gh', 'api', 'user'], capture_output=True, text=True)
        if r.returncode != 0: return False
        import json; u = json.loads(r.stdout); gn, gl = u.get('name') or u.get('login', ''), u.get('login', '')
        ge = u.get('email') or f"{gl}@users.noreply.github.com"
        gn and not n.stdout.strip() and sp.run(['git', 'config', '--global', 'user.name', gn], capture_output=True)
        ge and not e.stdout.strip() and sp.run(['git', 'config', '--global', 'user.email', ge], capture_output=True)
        return True
    except: return False

def run(args, wt_dir=None):
    wt_dir = wt_dir or os.path.expanduser("~/projects/aiosWorktrees")
    cwd = os.getcwd()
    skip = '--yes' in args or '-y' in args

    if _git(cwd, 'rev-parse', '--git-dir').returncode != 0:
        _git(cwd, 'init', '-b', 'main'); Path(os.path.join(cwd, '.gitignore')).touch()
        _git(cwd, 'add', '-A'); _git(cwd, 'commit', '-m', 'Initial commit'); print("✓ Initialized")
        if not shutil.which('gh') or sp.run(['gh', 'auth', 'status'], capture_output=True).returncode != 0:
            print("! gh not installed or not authenticated. Run: brew install gh && gh auth login"); return
        u = args[0] if args and '://' in args[0] else ('' if skip else input(f"Create '{os.path.basename(cwd)}' on GitHub? (y=public/p=private): ").strip())
        if u in 'y p yes private'.split() and sp.run(['gh', 'repo', 'create', os.path.basename(cwd), '--private' if 'p' in u else '--public', '--source', '.', '--push'], timeout=60).returncode == 0:
            print("✓ Pushed"); return
        if u and '://' in u: _git(cwd, 'remote', 'add', 'origin', u)

    ensure_git_cfg()
    r = _git(cwd, 'rev-parse', '--git-dir')
    is_wt = '.git/worktrees/' in r.stdout.strip() or cwd.startswith(wt_dir)
    args = [a for a in args if a not in ['--yes', '-y'] and '://' not in a]
    target = args[0] if args and os.path.isfile(os.path.join(cwd, args[0])) else None
    if target: args = args[1:]
    msg = ' '.join(args) or (f"Update {target}" if target else f"Update {os.path.basename(cwd)}")
    env = _env()

    if not is_wt:
        cur, main = _git(cwd, 'branch', '--show-current').stdout.strip(), _git_main(cwd)
        _git(cwd, 'add', target or '-A'); r = _git(cwd, 'commit', '-m', msg)
        if r.returncode == 0: print(f"✓ Committed: {msg}")
        elif 'nothing to commit' in r.stdout:
            if _git(cwd, 'remote').stdout.strip() and _git(cwd, 'rev-list', '--count', f'origin/{main}..HEAD').stdout.strip() == '0':
                print("[i] No changes"); sys.exit(0)
        else: _die(f"Commit failed: {r.stderr.strip() or r.stdout.strip()}")
        if cur != main:
            _git(cwd, 'checkout', main).returncode == 0 or _die(f"x Checkout failed")
            _git(cwd, 'merge', cur, '--no-edit', '-X', 'theirs').returncode == 0 or _die("x Merge failed")
            print(f"✓ Merged {cur} -> {main}")
        if not _git(cwd, 'remote').stdout.strip(): print("[i] Local only"); return
        _git(cwd, 'fetch', 'origin', env=env); _git_push(cwd, main, env) or sys.exit(1)
