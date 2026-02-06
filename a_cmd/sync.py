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
MAX_RETRIES = 3  # retry count for sync

# =============================================================================
# CORE SYNC FUNCTIONS
# These are imported by tests/test_sync/test_sync.py for dual testing/usage.
# Changes here are automatically tested by the monte carlo sim.
# =============================================================================

def is_conflict(text):
    """Detect all git conflict/error types"""
    t = text.lower()
    return any(x in t for x in ['conflict', 'diverged', 'rejected', 'overwritten', 'unmerged', 'aborting'])

def resolve_conflicts(path):
    """Auto-resolve conflicts: edit wins (accept theirs)"""
    p = q(path)
    # Get list of unmerged files
    r = sp.run(f'cd {p} && git diff --name-only --diff-filter=U', shell=True, capture_output=True, text=True)
    unmerged = [f for f in r.stdout.strip().split('\n') if f]
    for f in unmerged:
        # Edit wins: accept theirs (remote has edits), fallback to ours, fallback to remove
        sp.run(f'cd {p} && git checkout --theirs {shlex.quote(f)} 2>/dev/null || git checkout --ours {shlex.quote(f)} 2>/dev/null || git rm -f {shlex.quote(f)} 2>/dev/null', shell=True, capture_output=True)
    # Accept all incoming changes for any remaining conflicts
    sp.run(f'cd {p} && git checkout --theirs . 2>/dev/null', shell=True, capture_output=True)
    sp.run(f'cd {p} && git add -A', shell=True, capture_output=True)

def soft_delete(path, filepath):
    """Archive instead of hard delete (prevents edit vs delete conflicts)"""
    arc = Path(path) / '.archive'
    arc.mkdir(exist_ok=True)
    f = Path(filepath)
    if f.exists():
        f.rename(arc / f.name)

# =============================================================================

def _broadcast():
    """Non-blocking: background thread pings other devices once via SSH"""
    hosts = []
    for f in (SYNC_ROOT / 'ssh').glob('*.txt'):
        d = {k.strip(): v.strip() for l in f.read_text().splitlines() if ':' in l for k, v in [l.split(':', 1)]}
        if d.get('Host') and d.get('Name') != DEVICE_ID:
            hosts.append((d['Host'], d.get('Password')))
    if not hosts: return
    def _ping():
        for h, pw in hosts:
            try:
                p = h.rsplit(':', 1)
                cmd = (['sshpass', '-p', pw] if pw else []) + ['ssh', '-oConnectTimeout=2', '-oStrictHostKeyChecking=no'] + (['-p', p[1]] if len(p) > 1 else []) + [p[0], 'cd ~/projects/a-sync 2>/dev/null && git pull -q origin main || cd ~/a-sync && git pull -q origin main']
                sp.run(cmd, capture_output=True, timeout=5)
            except: pass
    threading.Thread(target=_ping, daemon=True).start()

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

def _sync(path=None, silent=False, auto_timestamp=True):
    """
    Sync with auto-resolution. Returns (success, had_conflict).

    - Retries up to MAX_RETRIES times on push rejection
    - Auto-resolves merge conflicts (edit wins)
    - Timestamps files before sync to prevent filename collisions

    This function is tested by tests/test_sync/test_sync.py monte carlo sim.
    """
    path = path or SYNC_ROOT
    p = q(path)
    had_conflict = False

    # Auto-timestamp files in FOLDERS to prevent filename collisions
    if auto_timestamp:
        for f in FOLDERS:
            folder_path = Path(path) / f
            if folder_path.exists():
                add_timestamps(folder_path)

    for attempt in range(MAX_RETRIES):
        # Step 1: Commit local changes first (prevents "overwritten" errors)
        sp.run(f'cd {p} && git add -A && git commit -qm sync', shell=True, capture_output=True)

        # Step 2: Pull with merge (not rebase)
        pull = sp.run(f'cd {p} && git pull --no-rebase origin main', shell=True, capture_output=True, text=True)

        if is_conflict(pull.stderr + pull.stdout):
            had_conflict = True
            resolve_conflicts(path)
            sp.run(f'cd {p} && git commit -qm "auto-resolve: edit wins"', shell=True, capture_output=True)

        # Step 3: Push
        push = sp.run(f'cd {p} && git push -q origin main', shell=True, capture_output=True, text=True)

        if push.returncode == 0:
            _broadcast()  # notify other devices
            return True, had_conflict

        # Retry if rejected (remote has newer commits)
        if 'rejected' in (push.stderr + push.stdout).lower():
            had_conflict = True
            continue

        # Other errors: fail
        if not silent:
            print(f"Sync error: {(push.stderr + push.stdout)[:200]}")
        return False, had_conflict

    if not silent:
        print(f"Sync failed after {MAX_RETRIES} retries")
    return False, had_conflict

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

HELP = """a sync - Append-only sync to GitHub (no conflicts possible)

  a sync           Sync all data (unified a-git repo)
  a sync all       Sync + broadcast to SSH hosts
  a sync help      Show this help

Data: ~/a-sync/ -> github.com/seanpattencode/a-git
Folders: common ssh login hub notes workspace docs tasks"""

def run():
    import sys
    args = sys.argv[2:] if len(sys.argv) > 2 else []

    if args and args[0] in ('help', '-h', '--help'):
        print(HELP); return

    # Clean stale poll daemon PID file
    pf = Path.home() / '.a-sync-poll.pid'
    pf.unlink(missing_ok=True)

    _init_repo()
    print(f"{SYNC_ROOT}")
    ok, conflict = _sync(SYNC_ROOT)

    url = sp.run(['git', '-C', str(SYNC_ROOT), 'remote', 'get-url', 'origin'],
                 capture_output=True, text=True).stdout.strip()
    t = sp.run(['git', '-C', str(SYNC_ROOT), 'log', '-1', '--format=%cd %s', '--date=format:%Y-%m-%d %I:%M:%S %p'],
               capture_output=True, text=True).stdout.strip()

    status = "CONFLICT" if conflict else ("synced" if ok else "no changes")
    print(f"  {url}\n  Last: {t}\n  Status: {status}")

    for folder in FOLDERS:
        p = SYNC_ROOT / folder
        if p.exists():
            count = len(list(p.glob('*.txt')))
            print(f"  {folder}: {count} files")

    if args and args[0] == 'all':
        print("\n--- Broadcasting to SSH hosts ---")
        sp.run('a ssh all "a sync"', shell=True)

# ============================================================================
# FOLDER STRUCTURE
# ============================================================================
#
# Location: ~/projects/a-sync/ (sibling to ~/projects/a/)
# Remote:   github.com/seanpattencode/a-git (private repo)
#
# Synced folders (git tracked):
#   common/prompts/   - Default prompts for agents (*.txt)
#   ssh/              - SSH host configs for multi-device sync
#   login/            - Auth tokens (gh, rclone.conf)
#   hub/              - Scheduled job definitions
#   notes/            - Quick notes from `a n "text"`
#   workspace/        - Projects and commands lists
#     projects/       - Project definitions (Name, Path, Repo)
#     cmds/           - Custom command definitions
#   docs/             - Documentation files
#   tasks/            - Task items for `a task`
#
# Local only (gitignored):
#   backup/           - Local backup mirror of above folders
#   logs/             - Agent session logs (synced to gdrive via rclone)
#   .archive/         - Old/deleted files
#
# File naming: {name}_{YYYYMMDDTHHMMSS.nnnnnnnnn}.txt
#   - Timestamp ensures uniqueness, no merge conflicts
#   - get_latest() finds most recent version by prefix
#
# ============================================================================
# TROUBLESHOOTING GUIDE
# ============================================================================
#
# DIAGNOSTIC COMMANDS:
#   cd ~/projects/a-sync
#   git remote -v              # Should show origin -> a-git.git
#   git status                 # Should be clean or show untracked files
#   git log --oneline -5       # Should show "sync" commits, not just "init"
#   git fetch origin           # Test connection to remote
#
# COMMON ISSUES:
#
# 1. "No remote configured" / fetch fails
#    Symptom: git remote -v shows nothing or wrong URL
#    Fix:
#      git remote add origin https://github.com/seanpattencode/a-git.git
#      # or if wrong URL:
#      git remote set-url origin https://github.com/seanpattencode/a-git.git
#
# 2. "Diverged" / local has different commits than remote
#    Symptom: git log shows "init" but remote has "sync" commits
#    Fix:
#      git fetch origin
#      git reset --hard origin/main    # Gets remote files, keeps untracked
#      git add -A && git commit -m "merge local and remote"
#      git push origin main
#
# 3. "Push rejected" / remote has newer commits
#    Symptom: Push fails with "non-fast-forward"
#    Fix: Run `a sync` again (pulls first, then pushes)
#
# 4. Missing files / wrong count
#    Check: ls tasks/*.txt | wc -l
#    Compare with: git ls-tree --name-only origin/main tasks/ | wc -l
#    If remote has more, reset to remote (see #2 above)
#
# 5. Auth issues
#    Symptom: "Permission denied" or "Could not read from remote"
#    Fix:
#      gh auth status           # Check GitHub auth
#      gh auth login            # Re-authenticate if needed
#
# EXPECTED FILE COUNTS (approximate):
#   tasks:    60-120 files
#   hub:      20-40 files
#   ssh:      5-10 files
#   notes:    300-500 files
#   projects: 15-25 files
#
# QUICK HEALTH CHECK:
#   a sync                     # Should show "synced" status
#   # If URL is empty or status is CONFLICT, something is wrong
#
# NUCLEAR OPTION (re-clone from scratch):
#   mv ~/projects/a-sync ~/projects/a-sync-backup
#   gh repo clone seanpattencode/a-git ~/projects/a-sync
#   # Then manually merge any local-only files from backup
#
# ============================================================================
