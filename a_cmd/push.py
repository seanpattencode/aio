"""aio push - first real, then instant for 10min"""
import sys, os, subprocess as sp, time

_DIR = os.path.expanduser('~/.local/share/a/logs')
_LOG, _OK = f'{_DIR}/push.log', f'{_DIR}/push.ok'
_TTL = 600  # 10 min

def run():
    cwd, msg = os.getcwd(), ' '.join(sys.argv[2:]) or f"Update {os.path.basename(os.getcwd())}"
    os.makedirs(_DIR, exist_ok=True)
    chg = sp.run(['git', 'status', '--porcelain'], cwd=cwd, capture_output=True, text=True).stdout.strip()
    tag = "✓" if chg else "○"  # ○ = clarification commit

    # Check if recent success (instant mode)
    if os.path.exists(_OK) and time.time() - os.path.getmtime(_OK) < _TTL:
        s = f'cd "{cwd}" && git add -A && git commit -m "{msg}" --allow-empty 2>/dev/null; git push 2>/dev/null; touch "{_OK}"'
        sp.Popen(['sh', '-c', s], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        print(f"{tag} {msg}")
        return

    # Real push (first time or expired) - skip repo create for worktrees
    sp.run(['git', 'config', 'remote.origin.url'], cwd=cwd, capture_output=True).returncode == 0 or sp.run(['gh', 'repo', 'create', '--private', '--source', '.', '--push'], cwd=cwd, capture_output=True)
    sp.run(['git', 'add', '-A'], cwd=cwd)
    sp.run(['git', 'commit', '-m', msg, '--allow-empty'], cwd=cwd, capture_output=True)
    r = sp.run(['git', 'push', '-u', 'origin', 'HEAD'], cwd=cwd, capture_output=True, text=True)
    if r.returncode == 0 or 'up-to-date' in r.stderr:
        open(_OK, 'w').close()
        print(f"{tag} {msg}")
    else:
        print(f"✗ {r.stderr.strip() or r.stdout.strip()}")
