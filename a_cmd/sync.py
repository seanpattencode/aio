# ============================================================================
# APPEND-ONLY SYNC - No conflicts possible
#
# Every file gets a timestamp: {name}_{YYYYMMDDTHHMMSS.nnnnnnnnn}.{ext}
# Git only sees new files = no merge conflicts = push always works
#
# Unified repo: a-git (contains common/ssh/login/hub/notes/workspace/docs/tasks)
# ============================================================================

"""a-sync folder sync:
  git+github:  ~/a-sync/ -> a-git repo (common ssh login hub notes workspace docs tasks)
  local only:  backup/ (gitignored)
  cloud only:  logs/ (rclone to gdrive, gitignored)
All files use append-only timestamps."""

import os, subprocess as sp, time, shlex
from pathlib import Path
from ._common import SYNC_ROOT, RCLONE_REMOTES, RCLONE_BACKUP_PATH, DEVICE_ID, get_rclone

FOLDERS = 'common ssh login hub notes workspace docs tasks'.split()

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
        print(HELP)
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

    if args and args[0] == 'all':
        print("\n--- Broadcasting to SSH hosts ---")
        sp.run('a ssh all "a sync"', shell=True)
