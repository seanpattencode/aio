#!/usr/bin/env python3
"""Test add/edit/delete/archive on unified a-git repo across devices"""
import subprocess as sp, time, sys
from pathlib import Path

ROOT = Path.home() / 'a-sync'
TS = time.strftime('%Y%m%dT%H%M%S') + f'.{time.time_ns() % 1000000000:09d}'
ERRORS = []

def run(cmd, desc=None):
    r = sp.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode:
        ERRORS.append(f"{desc or cmd}: {r.stderr[:100]}")
        return False, r.stdout.strip()
    return True, r.stdout.strip()

def sync_local():
    sp.run('cd ~/a-sync && git add -A && git commit -qm test', shell=True, capture_output=True)
    r = sp.run('cd ~/a-sync && git push origin main', shell=True, capture_output=True, text=True)
    if r.returncode and 'rejected' in r.stderr: ERRORS.append(f"local push rejected")

def sync_hsu():
    hsu('cd ~/projects/a-sync && git pull origin main')

def pull_local():
    sp.run('cd ~/a-sync && git pull origin main', shell=True, capture_output=True)

def hsu(cmd):
    # Escape quotes for nested shell
    escaped = cmd.replace("'", "'\\''")
    r = sp.run(f"a ssh hsu '{escaped}'", shell=True, capture_output=True, text=True)
    out = r.stdout + r.stderr
    # Filter out the 'a' banner output
    lines = [l for l in out.split('\n') if not l.startswith(('a c|', 'a <#>', 'a prompt', 'a help', 'Workspace:', 'PROJECTS:', 'COMMANDS:', '  ')) and not l.strip().startswith(('0.', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '~', '+', 'x'))]
    return r.returncode == 0, '\n'.join(lines).strip()

def test_local(name, folder, content, archive=False):
    d = ROOT / folder
    f = d / f'_test_{TS}.txt'
    f.write_text(content)
    print(f"  {name}: ADD")
    if archive:
        arc = d / '.archive'; arc.mkdir(exist_ok=True)
        f.rename(arc / f.name); (arc / f.name).unlink()
        print(f"  {name}: ARCHIVE+DELETE")
    else:
        f.unlink()
        print(f"  {name}: DELETE")

def test_cross_device():
    """Test editing same doc from both devices"""
    print("\n=== CROSS-DEVICE EDIT ===")
    fname = f'_crosstest_{TS}.txt'
    local_path = ROOT / 'tasks' / fname
    hsu_path = f'~/projects/a-sync/tasks/{fname}'

    # 1. Create on WSL
    local_path.write_text('v1-wsl\n')
    print(f"  WSL: created {fname}")
    sync_local()

    # 2. Pull and verify on hsu
    sync_hsu()
    ok, out = hsu(f'cat {hsu_path}')
    if 'v1-wsl' not in out:
        ERRORS.append(f"hsu didn't get WSL file: {out}")
        return False
    print(f"  HSU: verified v1-wsl")

    # 3. Edit on hsu (append-only: create new version)
    fname2 = f'_crosstest_{TS}.v2.txt'
    hsu_path2 = f'~/projects/a-sync/tasks/{fname2}'
    ok, _ = hsu(f'echo "v2-hsu" > {hsu_path2}')
    ok, _ = hsu('cd ~/projects/a-sync && git add -A && git commit -qm "hsu edit" && git push -q origin main')
    print(f"  HSU: created {fname2}")

    # 4. Pull and verify on WSL
    pull_local()
    local_path2 = ROOT / 'tasks' / fname2
    if not local_path2.exists() or 'v2-hsu' not in local_path2.read_text():
        ERRORS.append(f"WSL didn't get hsu edit")
        return False
    print(f"  WSL: verified v2-hsu")

    # Cleanup
    local_path.unlink(missing_ok=True)
    local_path2.unlink(missing_ok=True)
    sync_local()
    print(f"  CLEANUP: done")
    return True

def test_hsu_ops():
    """Test operations directly on hsu"""
    print("\n=== HSU OPERATIONS ===")
    fname = f'_hsutest_{TS}.txt'

    # Pull first to avoid divergence
    hsu('cd ~/projects/a-sync && git pull --no-rebase origin main')

    # Add on hsu
    ok, _ = hsu(f'echo "hsu test" > ~/projects/a-sync/common/{fname}')
    hsu('cd ~/projects/a-sync && git add -A && git commit -m "hsu add" && git push origin main')
    print(f"  HSU: ADD {fname}")

    # Verify on WSL
    pull_local()
    if not (ROOT / 'common' / fname).exists():
        ERRORS.append("WSL didn't get hsu add")
        return False
    print(f"  WSL: verified")

    # Delete on hsu
    ok, _ = hsu(f'rm ~/projects/a-sync/common/{fname}')
    ok, _ = hsu('cd ~/projects/a-sync && git add -A && git commit -qm "hsu del" && git push -q origin main')
    print(f"  HSU: DELETE")

    # Verify deletion on WSL
    pull_local()
    if (ROOT / 'common' / fname).exists():
        ERRORS.append("WSL still has deleted file")
        return False
    print(f"  WSL: verified deletion")
    return True

if __name__ == '__main__':
    print(f"Testing unified sync: {ROOT}")
    print(f"Timestamp: {TS}")

    # Local tests
    print("\n=== LOCAL OPERATIONS ===")
    sync_local()
    test_local('tasks', 'tasks', 'test\n')
    test_local('notes', 'notes', 'Text: test\nStatus: pending\n', archive=True)
    test_local('ssh', 'ssh', 'Name: _test\nHost: t@127.0.0.1\n')
    test_local('common', 'common', 'test\n')
    test_local('hub', 'hub', 'test\n')
    sync_local()

    # Cross-device tests
    test_cross_device()
    test_hsu_ops()

    # Broadcast test (uses a task add which triggers _broadcast via fork)
    print("\n=== BROADCAST TEST ===")
    bcast_id = str(int(time.time()))[-6:]  # last 6 digits
    sp.run(f'a task add "bcasttest{bcast_id}"', shell=True, capture_output=True)
    print(f"  WSL: added task 'bcasttest{bcast_id}' (triggers broadcast)")
    time.sleep(8)  # wait for forked broadcast (3 pings at 3s intervals)
    ok, out = hsu(f'ls ~/projects/a-sync/tasks/*bcasttest{bcast_id}*')
    if f'bcasttest{bcast_id}' in out:
        print("  HSU: received via broadcast - PASS")
    else:
        ERRORS.append("broadcast: hsu didn't receive file")
        print(f"  HSU: missing - FAIL (got: {out[:50]})")
    for f in ROOT.glob(f'tasks/*bcasttest{bcast_id}*'): f.unlink()
    sync_local()

    # Final status
    print("\n" + "="*40)
    if ERRORS:
        print(f"FAILED ({len(ERRORS)} errors):")
        for e in ERRORS: print(f"  x {e}")
        sys.exit(1)
    else:
        print("PASSED - all operations successful")
        sys.exit(0)
