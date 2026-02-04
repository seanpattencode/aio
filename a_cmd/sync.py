# ============================================================================
# APPEND-ONLY SYNC - No conflicts possible
#
# Every file gets a timestamp: {name}_{YYYYMMDDTHHMMSS.nnnnnnnnn}.{ext}
# Git only sees new files = no merge conflicts = push always works
#
# Unified repo: a-git (contains common/ssh/login/hub/notes/workspace/docs/tasks)
# ============================================================================
#
# MIGRATION NOTES (2026-02-03)
# ----------------------------
# Problem: Local ~/projects/a-sync/ had no git remote configured. Only had
# a single "init" commit while remote a-git repo had all the real data.
# Local and remote were completely diverged (51 local-only files, 69 remote-only).
#
# Fix steps:
#   1. Add missing remote:
#      git remote add origin https://github.com/seanpattencode/a-git.git
#
#   2. Fetch remote:
#      git fetch origin
#
#   3. Reset to remote (preserves untracked local files):
#      git reset --hard origin/main
#
#   4. Stage and commit local-only files to merge both sets:
#      git add -A && git commit -m "merge local and remote sync data"
#
#   5. Push merged data:
#      git push origin main
#
# Result: 114 tasks (combined), 39 hub, 8 ssh, 383 notes all synced.
#
# Old repos to delete (need delete_repo scope):
#   gh auth refresh -h github.com -s delete_repo
#   gh repo delete seanpattencode/test-sync-4 --yes
#   gh repo delete seanpattencode/test-sync-repo-3 --yes
#   gh repo delete seanpattencode/a-sync --yes
#   gh repo delete seanpattencode/aio-sync --yes
#   gh repo delete seanpattencode/aio-sync-archive --yes
#
# ============================================================================

"""a-sync folder sync:
  git+github:  ~/a-sync/ -> a-git repo (common ssh login hub notes workspace docs tasks)
  local only:  backup/ (gitignored)
  cloud only:  logs/ (rclone to gdrive, gitignored)
All files use append-only timestamps."""

import os, subprocess as sp, time, shlex, threading
from pathlib import Path
from ._common import SYNC_ROOT, RCLONE_REMOTES, RCLONE_BACKUP_PATH, DEVICE_ID, get_rclone

FOLDERS = 'common ssh login hub notes workspace docs tasks'.split()

def _broadcast():
    """Non-blocking: fork to ping all devices 3x at 3s intervals"""
    if os.fork() > 0: return  # parent returns immediately
    os.setsid()  # detach from terminal
    from concurrent.futures import ThreadPoolExecutor
    hosts = []
    for f in (SYNC_ROOT / 'ssh').glob('*.txt'):
        d = {k.strip(): v.strip() for l in f.read_text().splitlines() if ':' in l for k, v in [l.split(':', 1)]}
        if d.get('Host') and d.get('Name') != DEVICE_ID:
            hosts.append((d['Host'], d.get('Password')))
    for _ in range(3):
        def ping(hp):
            try:
                h, pw = hp; p = h.rsplit(':', 1)
                cmd = (['sshpass', '-p', pw] if pw else []) + ['ssh', '-oConnectTimeout=2', '-oStrictHostKeyChecking=no'] + (['-p', p[1]] if len(p) > 1 else []) + [p[0], 'cd ~/projects/a-sync 2>/dev/null && git pull -q origin main || cd ~/a-sync && git pull -q origin main']
                sp.run(cmd, capture_output=True, timeout=5)
            except: pass
        with ThreadPoolExecutor(max_workers=len(hosts) or 1) as ex: list(ex.map(ping, hosts))
        time.sleep(3)
    os._exit(0)

def q(p):
    """Quote path for shell"""
    return shlex.quote(str(p))

def ts():
    """Generate timestamp with nanosecond precision"""
    return time.strftime('%Y%m%dT%H%M%S') + f'.{time.time_ns() % 1000000000:09d}'

def add_timestamps(path, recursive=False):
    """Add timestamps to any files missing them (migration + new files)"""
    timestamp = ts()
    pattern = '**/*.txt' if recursive else '*.txt'
    for p in path.glob(pattern):
        if '_20' in p.stem:
            continue
        if p.name.startswith('.'):
            continue
        new_name = f'{p.stem}_{timestamp}{p.suffix}'
        p.rename(p.with_name(new_name))

def get_latest(path, name):
    """Get the latest version of a file by name prefix"""
    matches = sorted(path.glob(f'{name}_*.txt'))
    return matches[-1] if matches else None

def _sync(path=None, silent=False):
    """
    Append-only sync with conflict detection.
    Returns (success, conflict_detected)

    Flow: pull first, then commit local changes, then push.
    """
    path = path or SYNC_ROOT
    p = q(path)

    # Step 1: Pull remote changes first
    pull = sp.run(f'cd {p} && git pull -q --no-rebase origin main', shell=True, capture_output=True, text=True)

    if pull.returncode != 0:
        err = (pull.stderr + pull.stdout).lower()
        if 'conflict' in err or 'diverged' in err:
            if not silent:
                print(f"""
! Sync conflict (this shouldn't happen with append-only)

If you're SURE this device has the latest data:
  cd {path} && git add -A && git commit -m fix && git push --force

If unsure, ask AI:
  a c "help me resolve sync conflict in {path}"

Error: {(pull.stderr + pull.stdout)[:200]}
""")
            return False, True

    # Step 2: Add and commit local changes (ok if nothing to commit)
    sp.run(f'cd {p} && git add -A', shell=True, capture_output=True)
    commit = sp.run(f'cd {p} && git commit -qm sync', shell=True, capture_output=True, text=True)

    # Step 3: Push if we have commits to push
    if commit.returncode == 0:
        push = sp.run(f'cd {p} && git push -q origin main', shell=True, capture_output=True, text=True)
        if push.returncode != 0:
            err = (push.stderr + push.stdout).lower()
            if 'rejected' in err:
                if not silent:
                    print(f"""
! Push rejected (remote has changes, try sync again)

Error: {(push.stderr + push.stdout)[:200]}
""")
                return False, True
            return False, False
        _broadcast()  # notify other devices

    return True, False

def _merge_rclone():
    import re
    lc, rc = SYNC_ROOT/'login'/'rclone.conf', Path.home()/'.config/rclone/rclone.conf'
    if not lc.exists(): return
    rc.parent.mkdir(parents=True, exist_ok=True)
    lt, rt = lc.read_text(), rc.read_text() if rc.exists() else ''
    for n in 'a-gdrive', 'a-gdrive2':
        if f'[{n}]' not in rt and (m := re.search(rf'\[{n}\][^\[]*', lt)):
            rc.write_text(rt + m.group() + '\n')
            rt = rc.read_text()

def cloud_sync(local_path, name):
    rc = get_rclone()
    _merge_rclone()
    if not rc: return False, "no rclone"
    tar = f'{os.getenv("TMPDIR", "/tmp")}/{name}-{DEVICE_ID}.tar.zst'
    if sp.run(f'tar -cf - -C {local_path} . 2>/dev/null | zstd -q > {tar}', shell=True).returncode > 1:
        return False, "tar failed"
    ok = [r for r in RCLONE_REMOTES if sp.run([rc, 'copyto', tar, f'{r}:{RCLONE_BACKUP_PATH}/{name}/{DEVICE_ID}.tar.zst', '-q']).returncode == 0]
    Path(tar).unlink(missing_ok=True)
    return bool(ok), f"{'✓'*len(ok) or 'x'} {','.join(ok) or 'fail'}"

def sync(folder=None):
    """Sync the unified a-git repo (or just pull if folder specified for compat)"""
    return _sync(SYNC_ROOT)

def sync_file(path, content=None):
    """
    Sync a single file using append-only.
    If content provided, writes new version. Returns path to latest version.
    """
    path = Path(path)
    repo_path = path.parent
    name = path.stem.rsplit('_', 1)[0] if '_20' in path.stem else path.stem

    if content is not None:
        new_path = repo_path / f'{name}_{ts()}{path.suffix}'
        new_path.write_text(content)

    _sync(SYNC_ROOT, silent=True)
    return get_latest(repo_path, name)

def _init_repo():
    """Initialize or clone the a-git repo"""
    if (SYNC_ROOT / '.git').exists():
        return True

    r = sp.run(
        f'gh repo clone seanpattencode/a-git {q(SYNC_ROOT)} || '
        f'(cd {q(SYNC_ROOT)} && git init -q -b main && '
        f'echo "backup/\\nlogs/\\n.archive/" > .gitignore && '
        f'git add -A && git commit -qm init && '
        f'gh repo create a-git --private --source=. --push)',
        shell=True, capture_output=True, text=True
    )
    return r.returncode == 0

POLL_INTERVAL = 60  # seconds

def _poll_loop():
    """Background loop: pull every POLL_INTERVAL seconds"""
    while True:
        time.sleep(POLL_INTERVAL)
        sp.run(f'cd {q(SYNC_ROOT)} && git pull -q origin main', shell=True, capture_output=True)

def start_poll_daemon():
    """Start background poll loop (fork to background)"""
    import os
    pid_file = Path.home() / '.a-sync-poll.pid'
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)  # check if running
            print(f"Poll daemon already running (pid {pid})")
            return
        except OSError:
            pass  # not running, continue

    pid = os.fork()
    if pid > 0:
        pid_file.write_text(str(pid))
        print(f"Poll daemon started (pid {pid}, interval {POLL_INTERVAL}s)")
        return

    # Child process
    os.setsid()
    while True:
        time.sleep(POLL_INTERVAL)
        sp.run(f'cd {q(SYNC_ROOT)} && git pull -q origin main', shell=True, capture_output=True)

def stop_poll_daemon():
    """Stop background poll loop"""
    import os, signal
    pid_file = Path.home() / '.a-sync-poll.pid'
    if not pid_file.exists():
        print("Poll daemon not running")
        return
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink()
        print(f"Poll daemon stopped (pid {pid})")
    except OSError:
        pid_file.unlink()
        print("Poll daemon was not running")

HELP = """a sync - Append-only sync to GitHub (no conflicts possible)

  a sync           Sync all data (unified a-git repo)
  a sync all       Sync + broadcast to SSH hosts
  a sync poll      Start background poll daemon (60s interval)
  a sync stop      Stop poll daemon
  a sync help      Show this help

Data: ~/a-sync/ -> github.com/seanpattencode/a-git
Folders: common ssh login hub notes workspace docs tasks"""

def run():
    import sys
    args = sys.argv[2:] if len(sys.argv) > 2 else []

    if args and args[0] in ('help', '-h', '--help'):
        print(HELP)
        return

    if args and args[0] == 'poll':
        start_poll_daemon()
        return

    if args and args[0] == 'stop':
        stop_poll_daemon()
        return

    # Initialize if needed
    _init_repo()

    # Sync
    print(f"{SYNC_ROOT}")
    ok, conflict = _sync(SYNC_ROOT)

    url = sp.run(['git', '-C', str(SYNC_ROOT), 'remote', 'get-url', 'origin'],
                 capture_output=True, text=True).stdout.strip()
    t = sp.run(['git', '-C', str(SYNC_ROOT), 'log', '-1', '--format=%cd %s', '--date=format:%Y-%m-%d %I:%M:%S %p'],
               capture_output=True, text=True).stdout.strip()

    status = "CONFLICT" if conflict else ("synced" if ok else "no changes")
    print(f"  {url}\n  Last: {t}\n  Status: {status}")

    # Show folder stats
    for folder in FOLDERS:
        p = SYNC_ROOT / folder
        if p.exists():
            count = len(list(p.glob('*.txt')))
            print(f"  {folder}: {count} files")

    # Show daemon status
    pid_file = Path.home() / '.a-sync-poll.pid'
    daemon_running = False
    if pid_file.exists():
        try:
            import os
            os.kill(int(pid_file.read_text().strip()), 0)
            daemon_running = True
        except: pass
    if daemon_running:
        print(f"\n  Poll: running ({POLL_INTERVAL}s) - stop with: a sync stop")
    else:
        print(f"\n  Poll: not running - start with: a sync poll")

    if args and args[0] == 'all':
        print("\n--- Broadcasting to SSH hosts ---")
        sp.run('a ssh all "a sync"', shell=True)
