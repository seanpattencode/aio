"""aio push - Commit and push"""
import sys, os, subprocess as sp, shutil
from pathlib import Path
from . _common import init_db, load_cfg, load_proj, _git, _git_main, _git_push, _env, _die, ensure_git_cfg, _in_repo

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees"))
    cwd, skip = os.getcwd(), '--yes' in sys.argv or '-y' in sys.argv

    if not _in_repo(cwd):
        _git(cwd, 'init', '-b', 'main'); Path(os.path.join(cwd, '.gitignore')).touch(); _git(cwd, 'add', '-A'); _git(cwd, 'commit', '-m', 'Initial commit'); print("✓ Initialized")
        if not shutil.which('gh') or sp.run(['gh', 'auth', 'status'], capture_output=True).returncode != 0:
            print("! gh not installed or not authenticated. Run: brew install gh && gh auth login"); return
        u = sys.argv[2] if len(sys.argv) > 2 and '://' in sys.argv[2] else ('' if skip else input(f"Create '{os.path.basename(cwd)}' on GitHub? (y=public/p=private): ").strip())
        if u in 'y p yes private'.split() and sp.run(['gh', 'repo', 'create', os.path.basename(cwd), '--private' if 'p' in u else '--public', '--source', '.', '--push'], timeout=60).returncode == 0: print("✓ Pushed"); return
        if u and '://' in u: _git(cwd, 'remote', 'add', 'origin', u)

    ensure_git_cfg(); r = _git(cwd, 'rev-parse', '--git-dir'); is_wt = '.git/worktrees/' in r.stdout.strip() or cwd.startswith(WT_DIR)
    args = [a for a in sys.argv[2:] if a not in ['--yes', '-y'] and '://' not in a]
    target = args[0] if args and os.path.isfile(os.path.join(cwd, args[0])) else None
    if target: args = args[1:]
    msg = ' '.join(args) or (f"Update {target}" if target else f"Update {os.path.basename(cwd)}")
    env = _env()

    if is_wt:
        wn = os.path.basename(cwd)
        proj = next((p for p in PROJ if wn.startswith(os.path.basename(p) + '-')), None) or _die(f"x Could not find project for {wn}")
        wb = _git(cwd, 'branch', '--show-current').stdout.strip()
        print(f"Worktree: {wn} | Branch: {wb} | Msg: {msg}")
        to_main = skip or input("Push to: 1=main 2=branch [1]: ").strip() != '2'
        _git(cwd, 'add', target or '-A'); r = _git(cwd, 'commit', '-m', msg)
        r.returncode == 0 and print(f"✓ Committed: {msg}")
        if to_main:
            main = _git_main(proj); _git(proj, 'fetch', 'origin', env=env)
            ahead = _git(proj, 'rev-list', '--count', f'origin/{main}..{main}').stdout.strip()
            if ahead and int(ahead) > 0:
                ol = set(_git(cwd, 'diff', '--name-only', f'origin/{main}...HEAD').stdout.split()) & set(_git(proj, 'diff', '--name-only', f'origin/{main}..{main}').stdout.split()) - {''}
                m = f"[i] {main} {ahead} ahead (different files)\nMerge?" if not ol else f"! {main} {ahead} ahead, overlap: {', '.join(ol)}\n{_git(proj, 'log', f'origin/{main}..{main}', '--oneline').stdout.strip()}\nContinue?"
                skip or input(f"{m} (y/n): ").lower() in ['y', 'yes'] or _die("x Cancelled")
            _git(proj, 'checkout', main).returncode == 0 or _die(f"x Checkout {main} failed")
            _git(proj, 'merge', wb, '--no-edit', '-X', 'theirs').returncode == 0 or _die("x Merge failed")
            print(f"✓ Merged {wb} -> {main}"); _git_push(proj, main, env) or sys.exit(1)
            _git(proj, 'fetch', 'origin', env=env); _git(proj, 'reset', '--hard', f'origin/{main}')
            if not skip and input(f"\nDelete worktree '{wn}'? (y/n): ").strip().lower() in ['y', 'yes']:
                _git(proj, 'worktree', 'remove', '--force', cwd); _git(proj, 'branch', '-D', f'wt-{wn}')
                import shutil as sh; os.path.exists(cwd) and sh.rmtree(cwd); print("✓ Cleaned up worktree")
                os.chdir(proj); os.execvp(os.environ.get('SHELL', 'bash'), [os.environ.get('SHELL', 'bash')])
        else: _git(cwd, 'push', '-u', 'origin', wb, env=env) and print(f"✓ Pushed to {wb}")
    else:
        cur, main = _git(cwd, 'branch', '--show-current').stdout.strip(), _git_main(cwd)
        _git(cwd, 'add', target or '-A'); r = _git(cwd, 'commit', '-m', msg)
        if r.returncode == 0: print(f"✓ Committed: {msg}")
        elif 'nothing to commit' in r.stdout:
            if _git(cwd, 'remote').stdout.strip() and _git(cwd, 'rev-list', '--count', f'origin/{main}..HEAD').stdout.strip() == '0': print("[i] No changes"); sys.exit(0)
        else: _die(f"Commit failed: {r.stderr.strip() or r.stdout.strip()}")
        if cur != main:
            _git(cwd, 'checkout', main).returncode == 0 or _die(f"x Checkout failed")
            _git(cwd, 'merge', cur, '--no-edit', '-X', 'theirs').returncode == 0 or _die("x Merge failed"); print(f"✓ Merged {cur} -> {main}")
        if not _git(cwd, 'remote').stdout.strip(): print("[i] Local only"); return
        _git(cwd, 'fetch', 'origin', env=env); _git_push(cwd, main, env) or sys.exit(1)
