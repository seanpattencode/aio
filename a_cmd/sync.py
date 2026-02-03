# ============================================================================
# APPEND-ONLY SYNC - No conflicts possible
#
# Every file gets a timestamp: {name}_{YYYYMMDDTHHMMSS.nnnnnnnnn}.{ext}
# Git only sees new files = no merge conflicts = push always works
#
# See ideas/APPEND_ONLY_SYNC.md for design doc
# See projects/sync_test/ for monte carlo validation (1000 ops, 0 conflicts)
# ============================================================================

"""a-sync folder sync:
  local only:  backup/<repo>/  (pre-sync snapshot)
  git+github:  common ssh login hub notes workspace docs tasks
  cloud only:  logs (a log sync → gdrive tar.zst, too large for git)
All git repos use main branch. All files use append-only timestamps."""

import os, subprocess as sp, time, shlex
from pathlib import Path
from ._common import SYNC_ROOT, RCLONE_REMOTES, RCLONE_BACKUP_PATH, DEVICE_ID, get_rclone

REPOS = {k: f'a-{k}' for k in 'common ssh login hub notes workspace docs tasks'.split()}

def q(p):
    """Quote path for shell"""
    return shlex.quote(str(p))

def ts():
    """Generate timestamp with nanosecond precision"""
    return time.strftime('%Y%m%dT%H%M%S') + f'.{time.time_ns() % 1000000000:09d}'

def add_timestamps(path):
    """Add timestamps to any files missing them (migration + new files)"""
    timestamp = ts()
    for p in path.glob('*.txt'):
        # Skip if already has timestamp (contains _20 pattern like _20260203)
        if '_20' in p.stem:
            continue
        # Skip hidden/special files
        if p.name.startswith('.'):
            continue
        new_name = f'{p.stem}_{timestamp}{p.suffix}'
        p.rename(p.with_name(new_name))

def get_latest(path, name):
    """Get the latest version of a file by name prefix"""
    matches = sorted(path.glob(f'{name}_*.txt'))
    return matches[-1] if matches else None

def _sync(path, silent=False):
    """
    Append-only sync with conflict detection.
    Returns (success, conflict_detected)
    """
    r = sp.run(
        f'cd {q(path)} && git add -A && git commit -qm sync && git pull -q --no-rebase origin main && git push -q origin main',
        shell=True, capture_output=True, text=True
    )

    if r.returncode != 0:
        err = (r.stderr + r.stdout).lower()
        if 'conflict' in err or 'diverged' in err or 'rejected' in err:
            if not silent:
                print(f"""
! Sync conflict (this shouldn't happen with append-only)

If you're SURE this device has the latest data:
  cd {path} && git add -A && git commit -m fix && git push --force

If unsure, ask AI:
  a c "help me resolve sync conflict in {path}"

Error: {(r.stderr + r.stdout)[:200]}
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

def _sync_repo(path, repo_name, msg='sync'):
    """Sync a repo using append-only strategy"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    # Local backup before sync
    b = SYNC_ROOT / 'backup' / path.name
    if path.exists():
        sp.run(f'mkdir -p {q(b.parent)} && rm -rf {q(b)} && cp -r {q(path)} {q(b)}', shell=True, capture_output=True)

    # Check if repo exists
    has_remote = sp.run(f'git -C {q(path)} remote get-url origin', shell=True, capture_output=True).returncode == 0

    if has_remote:
        # Add timestamps to any files missing them
        add_timestamps(path)

        # Ensure on main branch
        br = sp.run(f'git -C {q(path)} branch --show-current', shell=True, capture_output=True, text=True).stdout.strip() or 'main'
        if br == 'master':
            print(f"⚠ [{repo_name}] on master, switching to main...")
            sp.run(f'cd {q(path)} && git checkout main 2>/dev/null || git checkout -b main', shell=True, capture_output=True)

        # Sync with conflict detection
        ok, conflict = _sync(path)

        if conflict:
            return f"CONFLICT - see above"

    else:
        # Clone or create repo
        r = sp.run(
            f'rm -rf {q(path)}; gh repo clone {repo_name} {q(path)} || '
            f'(mkdir -p {q(path)} && cd {q(path)} && git init -q && echo "# {repo_name}" > README.md && '
            f'git add -A && git commit -qm init && gh repo create {repo_name} --private --source=. --push)',
            shell=True, capture_output=True, text=True
        )
        if r.returncode:
            err = (r.stderr or r.stdout or '').strip().split('\n')[-1]
            print(f"x [{repo_name}] {err}")
            return "error"

    url = sp.run(['git', '-C', str(path), 'remote', 'get-url', 'origin'], capture_output=True, text=True).stdout.strip() or 'local'
    return url

def sync(repo='common', msg='sync'):
    """Sync a single repo"""
    return _sync_repo(SYNC_ROOT / repo, REPOS.get(repo, f'a-{repo}'), msg)

def sync_file(path, content=None):
    """
    Sync a single file using append-only.
    If content provided, writes new version. Returns path to latest version.
    """
    path = Path(path)
    repo_path = path.parent
    name = path.stem.rsplit('_', 1)[0] if '_20' in path.stem else path.stem

    if content is not None:
        # Write new version with timestamp
        new_path = repo_path / f'{name}_{ts()}{path.suffix}'
        new_path.write_text(content)

    # Sync the repo
    _sync(repo_path, silent=True)

    # Return latest version
    return get_latest(repo_path, name)

HELP = """a sync - Append-only sync to GitHub (no conflicts possible)

  a sync           Sync all repos
  a sync <repo>    Sync specific repo (common/ssh/login/hub/notes/workspace/docs/tasks)
  a sync all       Sync all + broadcast to SSH hosts
  a sync help      Show this help

Repos: common ssh login hub notes workspace docs tasks"""

def run():
    import sys
    args = sys.argv[2:] if len(sys.argv) > 2 else []

    if not args or args[0] in ('help', '-h', '--help'):
        if args and args[0] in ('help', '-h', '--help'):
            print(HELP)
            return

    # Single repo sync
    if args and args[0] in REPOS:
        repo = args[0]
        path = SYNC_ROOT / repo
        url = _sync_repo(path, REPOS[repo])
        t = sp.run(['git', '-C', str(path), 'log', '-1', '--format=%cd %s', '--date=format:%Y-%m-%d %I:%M:%S %p'],
                   capture_output=True, text=True).stdout.strip()
        print(f"[{repo}] {url}\nLast: {t}")
        return

    # All repos
    print(SYNC_ROOT)
    for repo, name in REPOS.items():
        path = SYNC_ROOT / repo
        url = _sync_repo(path, name)
        t = sp.run(['git', '-C', str(path), 'log', '-1', '--format=%cd %s', '--date=format:%Y-%m-%d %I:%M:%S %p'],
                   capture_output=True, text=True).stdout.strip()
        print(f"\n[{repo}] {url}\nLast: {t}")

    if args and args[0] == 'all':
        print("\n--- Broadcasting to SSH hosts ---")
        sp.run('a ssh all "a sync"', shell=True)
