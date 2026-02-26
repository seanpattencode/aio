"""
Sync test - imports directly from a_cmd/sync.py for dual testing/usage.
Changes to sync.py are automatically tested here via monte carlo sim.

Usage:
    python test_sync.py monte    # Run monte carlo (n=1000)
    python test_sync.py race     # Test race condition
    python test_sync.py          # List available tests
"""
import sys, random
from pathlib import Path

# Import production sync functions directly - this ensures tests match production
sys.path.insert(0, str(Path(__file__).parents[2] / 'lib'))
from sync import q, ts, is_conflict, resolve_conflicts, add_timestamps, soft_delete, _sync, MAX_RETRIES
import subprocess as sp

# === TEST HARNESS ===
ROOT = Path(__file__).parent / 'devices'
DEVICES = ('device_a', 'device_b', 'device_c')

def setup():
    """Create fresh test repos"""
    sp.run(f'rm -rf {q(ROOT)} && mkdir -p {q(ROOT/"origin")} && git -C {q(ROOT/"origin")} init -q -b main --bare', shell=True)
    for d in DEVICES:
        sp.run(f'mkdir -p {q(ROOT/d)} && git -C {q(ROOT/d)} init -q -b main && git -C {q(ROOT/d)} remote add origin {q(ROOT/"origin")}', shell=True)

def pull(device):
    """Pull with auto-commit and conflict resolution (uses production functions)"""
    d = ROOT / device
    p = q(d)
    sp.run(f'cd {p} && git add -A && git commit -qm "pre-pull"', shell=True, capture_output=True)
    r = sp.run(f'cd {p} && git pull --no-rebase origin main', shell=True, capture_output=True, text=True)
    if is_conflict(r.stderr + r.stdout):
        resolve_conflicts(d)
        sp.run(f'cd {p} && git commit -qm "auto-resolve"', shell=True, capture_output=True)

def create_file(device, name, content=''):
    """Create timestamped file and push"""
    p = ROOT / device / f'{name}_{ts()}.txt'
    p.write_text(content or f'created by {device}')
    sp.run(f'cd {q(ROOT/device)} && git add -A && git commit -qm "add {p.name}" && git push -u origin main', shell=True, capture_output=True)
    return p.name

def sync(device, silent=True):
    """Sync device using production _sync (without auto_timestamp for test control)"""
    return _sync(ROOT / device, silent=silent, auto_timestamp=False)

def sync_edit(device, silent=True):
    """Sync with edit detection: rename modified files to new timestamp"""
    d = ROOT / device
    t = ts()
    arc = d / '.archive'
    arc.mkdir(exist_ok=True)
    for p in d.glob('*.txt'):
        r = sp.run(f'git -C {q(d)} diff --quiet {q(str(p.name))}', shell=True)
        if r.returncode:  # file was modified
            old = sp.run(f'git -C {q(d)} show HEAD:{q(str(p.name))}', shell=True, capture_output=True, text=True)
            if old.stdout:
                (arc / p.name).write_text(old.stdout)
            base = p.stem.rsplit('_', 1)[0] if '_20' in p.stem else p.stem
            p.rename(p.with_name(f'{base}_{t}{p.suffix}'))
    return _sync(d, silent=silent, auto_timestamp=False)

# === CONFLICT TESTS ===

def test_race(n=5):
    """Two devices push without pull - auto-resolved via retry"""
    setup(); create_file('device_a', 'seed'); [pull(d) for d in DEVICES]
    resolved = []
    for i in range(n):
        (ROOT/'device_a'/f'race_a_{i}.txt').write_text(f'a{i}')
        (ROOT/'device_b'/f'race_b_{i}.txt').write_text(f'b{i}')
        ok1, c1 = sync('device_a')
        ok2, c2 = sync('device_b')
        if c1 or c2: resolved.append((i, 'a' if c1 else '', 'b' if c2 else ''))
        [pull(d) for d in DEVICES]
    counts = {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}
    return {'iterations': n, 'resolved': len(resolved), 'counts': counts, 'match': len(set(counts.values()))==1}

def test_offline_bulk(n=10):
    """Device offline, accumulates changes, then syncs"""
    setup(); create_file('device_a', 'seed'); [pull(d) for d in DEVICES]
    for i in range(n):
        (ROOT/'device_a'/f'online_a_{i}.txt').write_text(f'a{i}')
        sync('device_a'); pull('device_b')
        (ROOT/'device_b'/f'online_b_{i}.txt').write_text(f'b{i}')
        sync('device_b'); pull('device_a')
    for i in range(n):
        (ROOT/'device_c'/f'offline_{i}.txt').write_text(f'c{i}')
    ok, conflict = sync('device_c')
    [pull(d) for d in DEVICES]
    counts = {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}
    return {'online': n*2, 'offline': n, 'conflict': conflict, 'counts': counts, 'match': len(set(counts.values()))==1}

def test_edit_same_file(n=5):
    """Two devices edit same file - both preserved via timestamp rename"""
    setup(); fname = create_file('device_a', 'shared'); [pull(d) for d in DEVICES]
    resolved = []
    for i in range(n):
        (ROOT/'device_a'/fname).write_text(f'edit_a_{i}')
        (ROOT/'device_b'/fname).write_text(f'edit_b_{i}')
        ok1, c1 = sync_edit('device_a')
        ok2, c2 = sync_edit('device_b')
        if c1 or c2: resolved.append((i, c1, c2))
        [pull(d) for d in DEVICES]
        files = sorted((ROOT/'device_a').glob('shared_*.txt'))
        fname = files[-1].name if files else fname
    counts = {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}
    archive = {d: len(list((ROOT/d/'.archive').glob('*.txt'))) if (ROOT/d/'.archive').exists() else 0 for d in DEVICES}
    return {'iterations': n, 'resolved': len(resolved), 'counts': counts, 'archive': archive, 'match': len(set(counts.values()))==1}

def test_delete_race():
    """Two devices archive same file - both want same outcome"""
    setup(); fname = create_file('device_a', 'todelete'); [pull(d) for d in DEVICES]
    for d in ['device_a', 'device_b']:
        soft_delete(ROOT/d, ROOT/d/fname)
    ok1, c1 = sync('device_a')
    ok2, c2 = sync('device_b')
    [pull(d) for d in DEVICES]
    counts = {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}
    archived = {d: len(list((ROOT/d/'.archive').glob('*.txt'))) if (ROOT/d/'.archive').exists() else 0 for d in DEVICES}
    return {'resolved': c1 or c2, 'counts': counts, 'archived': archived, 'match': len(set(counts.values()))==1}

def test_edit_delete_race():
    """Device A edits, Device B archives - edit wins"""
    setup(); fname = create_file('device_a', 'shared'); [pull(d) for d in DEVICES]
    (ROOT/'device_a'/fname).write_text('edited by a')
    ok1, c1 = sync_edit('device_a')
    soft_delete(ROOT/'device_b', ROOT/'device_b'/fname)
    ok2, c2 = sync('device_b')
    [pull(d) for d in DEVICES]
    files = {d: [f.name for f in (ROOT/d).glob('*.txt')] for d in DEVICES}
    edit_preserved = all(len(f) > 0 for f in files.values())
    return {'edit_preserved': edit_preserved, 'files': files, 'resolved': c1 or c2}

# === MONTE CARLO ===

def monte_carlo(n=1000, verbose=False):
    """Random operations across devices - should result in 0 conflicts and all match"""
    setup(); create_file('device_a', 'seed'); [pull(d) for d in DEVICES]
    for d in DEVICES:
        (ROOT/d/'nested').mkdir(exist_ok=True)
        sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "mkdir" && git push origin main', shell=True, capture_output=True)
    [pull(d) for d in DEVICES]

    # Create hub-style and rclone-style files (append-only timestamped)
    for d in DEVICES:
        (ROOT/d/'agents').mkdir(exist_ok=True)
        (ROOT/d/'login').mkdir(exist_ok=True)
        (ROOT/d/'agents'/f'checker_{ts()}.txt').write_text('Name: checker\nSchedule: 8:00\nEnabled: true\nLast-Run: \n')
        (ROOT/d/'agents'/f'backup_{ts()}.txt').write_text('Name: backup\nSchedule: 12:00\nEnabled: true\nLast-Run: \n')
        (ROOT/d/'login'/f'rclone_{ts()}.conf').write_text('[a-gdrive]\ntoken = initial\n')
        sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "init hub+rclone" && git push origin main', shell=True, capture_output=True)
    [pull(d) for d in DEVICES]

    conflicts, errors, reseeds = [], [], 0
    ops = ['add', 'delete', 'archive', 'edit', 'edit_raw', 'nested', 'non_txt', 'hub_edit', 'rclone_edit']

    for i in range(n):
        d = random.choice(DEVICES)
        op = random.choice(ops)

        try:
            pull(d)
            files = list((ROOT/d).glob('*.txt'))

            if not files:
                if verbose: print(f"[{i}] reseed {d}")
                (ROOT/d/f'reseed_{i}.txt').write_text(f'reseed {i}')
                sync(d)
                reseeds += 1
                continue

            if op == 'add':
                (ROOT/d/f'f{i}.txt').write_text(f'{i}')
                ok, c = sync(d)
                if c: conflicts.append((i, d, 'add'))
            elif op == 'delete' and files:
                soft_delete(ROOT/d, random.choice(files))
                ok, c = sync(d)
                if c: conflicts.append((i, d, 'delete'))
            elif op == 'archive' and files:
                soft_delete(ROOT/d, random.choice(files))
                ok, c = sync(d)
                if c: conflicts.append((i, d, 'archive'))
            elif op == 'edit' and files:
                random.choice(files).write_text(f'edit{i}')
                ok, c = sync_edit(d)
                if c: conflicts.append((i, d, 'edit'))
            elif op == 'edit_raw' and files:
                random.choice(files).write_text(f'raw{i}')
                ok, c = sync(d)
                if c: conflicts.append((i, d, 'edit_raw'))
            elif op == 'nested':
                (ROOT/d/'nested'/f'n{i}.txt').write_text(f'{i}')
                ok, c = sync(d)
                if c: conflicts.append((i, d, 'nested'))
            elif op == 'non_txt':
                ext = random.choice(['.json', '.md', '.yaml'])
                (ROOT/d/f'file{i}{ext}').write_text(f'{i}')
                ok, c = sync(d)
                if c: conflicts.append((i, d, 'non_txt'))
            elif op == 'hub_edit':
                # Simulates hub_save: append-only timestamped file per save
                agent = random.choice(['checker', 'backup'])
                (ROOT/d/'agents'/f'{agent}_{ts()}.txt').write_text(f'Name: {agent}\nSchedule: 8:00\nEnabled: true\nLast-Run: 2026-01-{i%28+1:02d}\n')
                ok, c = sync(d)
                if c: conflicts.append((i, d, 'hub_edit'))
            elif op == 'rclone_edit':
                # Simulates rclone token refresh: append-only timestamped conf
                (ROOT/d/'login'/f'rclone_{ts()}.conf').write_text(f'[a-gdrive]\ntoken = refreshed_{d}_{i}\n')
                ok, c = sync(d)
                if c: conflicts.append((i, d, 'rclone_edit'))

        except Exception as e:
            errors.append((i, d, op, str(e)))
            if verbose: print(f"[{i}] {d} {op}: {e}")

    [pull(d) for d in DEVICES]
    counts = {d: (
        len(list((ROOT/d).glob('*.txt'))),
        len(list((ROOT/d/'.archive').glob('*.txt'))) if (ROOT/d/'.archive').exists() else 0,
        len(list((ROOT/d/'nested').glob('*.txt'))) if (ROOT/d/'nested').exists() else 0,
    ) for d in DEVICES}
    by_op = {op: len([c for c in conflicts if c[2]==op]) for op in ops}

    return {
        'actions': n,
        'errors': len(errors),
        'conflicts': len(conflicts),
        'by_op': {k:v for k,v in by_op.items() if v},
        'reseeds': reseeds,
        'counts': counts,
        'match': len(set(counts.values())) == 1,
        'error_details': errors[:5] if errors else []
    }

def test_hub_conflict(n=10):
    """Two devices write hub agent files - append-only: each writes new timestamped file"""
    setup(); create_file('device_a', 'seed'); [pull(d) for d in DEVICES]
    for d in DEVICES:
        (ROOT/d/'agents').mkdir(exist_ok=True)
        (ROOT/d/'agents'/f'checker_{ts()}.txt').write_text('Name: checker\nSchedule: 8:00\nEnabled: true\nLast-Run: \n')
        sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "init hub" && git push origin main', shell=True, capture_output=True)
    [pull(d) for d in DEVICES]
    conflicts = []
    for i in range(n):
        # Both devices write NEW timestamped files (append-only, no edit-in-place)
        (ROOT/'device_a'/'agents'/f'checker_{ts()}.txt').write_text(f'Name: checker\nSchedule: 8:00\nEnabled: true\nLast-Run: 2026-01-{i:02d} from A\n')
        (ROOT/'device_b'/'agents'/f'checker_{ts()}.txt').write_text(f'Name: checker\nSchedule: 8:00\nEnabled: true\nLast-Run: 2026-01-{i:02d} from B\n')
        ok1, c1 = sync('device_a')
        ok2, c2 = sync('device_b')
        if c1 or c2: conflicts.append((i, 'a' if c1 else '', 'b' if c2 else ''))
        [pull(d) for d in DEVICES]
    counts = {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}
    return {'iterations': n, 'conflicts': len(conflicts), 'conflict_details': conflicts[:5], 'counts': counts, 'match': len(set(counts.values()))==1}

def test_rclone_conflict(n=10):
    """Two devices save rclone tokens - append-only: each writes new timestamped conf"""
    setup(); create_file('device_a', 'seed'); [pull(d) for d in DEVICES]
    for d in DEVICES:
        (ROOT/d/'login').mkdir(exist_ok=True)
        (ROOT/d/'login'/f'rclone_{ts()}.conf').write_text('[a-gdrive]\ntoken = initial\n')
        sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "init rclone" && git push origin main', shell=True, capture_output=True)
    [pull(d) for d in DEVICES]
    conflicts = []
    for i in range(n):
        (ROOT/'device_a'/'login'/f'rclone_{ts()}.conf').write_text(f'[a-gdrive]\ntoken = refresh_a_{i}\n')
        (ROOT/'device_b'/'login'/f'rclone_{ts()}.conf').write_text(f'[a-gdrive]\ntoken = refresh_b_{i}\n')
        ok1, c1 = sync('device_a')
        ok2, c2 = sync('device_b')
        if c1 or c2: conflicts.append((i, 'a' if c1 else '', 'b' if c2 else ''))
        [pull(d) for d in DEVICES]
    return {'iterations': n, 'conflicts': len(conflicts), 'conflict_details': conflicts[:5]}

# === TEST RUNNER ===

TESTS = {
    'race': test_race,
    'offline': test_offline_bulk,
    'edit_same': test_edit_same_file,
    'delete_race': test_delete_race,
    'edit_delete': test_edit_delete_race,
    'monte': monte_carlo,
    'hub': test_hub_conflict,
    'rclone': test_rclone_conflict,
}

def sim(name=None, timeout=60):
    """Run a test with timeout. Usage: sim('race') or sim()"""
    import signal
    if name is None:
        print("Available:", ', '.join(TESTS.keys()))
        return
    if name not in TESTS:
        print(f"Unknown: {name}. Available: {', '.join(TESTS.keys())}")
        return
    def handler(sig, frame): raise TimeoutError(f"Timeout {timeout}s")
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout)
    try:
        result = TESTS[name]()
        signal.alarm(0)
        return result
    except TimeoutError as e:
        return {'error': str(e)}

if __name__ == '__main__':
    import json
    if len(sys.argv) > 1:
        print(json.dumps(sim(sys.argv[1]), indent=2))
    else:
        sim()
