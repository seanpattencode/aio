#!/usr/bin/env python3
"""Monte Carlo sim: priority task operations - no data loss, perf targets
Run: python tests/test_priority/test_priority.py"""
import os, time, random, string, re, shutil
from pathlib import Path

# === CORE LOGIC (identical to task.py implementation) ===
_RE_PRI = re.compile(r'^\d{3}~')

def ts():
    """Nanosecond timestamp"""
    return time.strftime('%Y%m%dT%H%M%S') + f'.{time.time_ns() % 1000000000:09d}'

def slug(text):
    """Sanitize to alnum + hyphen"""
    s = text[:20].replace(' ', '-').lower()
    return ''.join(c for c in s if c.isalnum() or c == '-') or 'task'

def add(d, text, pri='500'):
    """Add task with priority - O(1)"""
    f = d / f'{pri}~{slug(text)}_{ts()}.txt'
    f.write_text(text + '\n')
    return f

def ls(d):
    """List tasks sorted by priority (filename sort) - O(n log n)"""
    return sorted([f for f in d.glob('*.txt') if _RE_PRI.match(f.name)], key=lambda f: f.name)

def delete(f):
    """Delete task (archive) - O(1)"""
    arc = f.parent / '.archive'
    arc.mkdir(exist_ok=True)
    f.rename(arc / f.name)

def rerank(f, new_pri):
    """Change priority - rename only, O(1)"""
    new = f.parent / (f'{new_pri}~' + f.name.split('~', 1)[1])
    f.rename(new)
    return new

def midpoint(a, b):
    """Fractional priority between a and b"""
    a, b = a or '000', b or '999'
    ai, bi = int(a.ljust(6, '0')[:6]), int(b.ljust(6, '0')[:6])
    if bi - ai <= 1:
        return str((ai * 10 + bi * 10) // 2).zfill(6)[:len(a)+1]
    return str((ai + bi) // 2).zfill(len(a))[:3]

def normalize(d):
    """Normalize manual files (no priority prefix)"""
    for f in d.glob('*.txt'):
        if f.name.startswith('.') or _RE_PRI.match(f.name):
            continue
        new = f'500~{slug(f.stem)}_{ts()}.txt'
        f.rename(d / new)

# === MONTE CARLO SIM ===

def run_sim(duration=10, seed=42):
    random.seed(seed)
    d = Path.home() / '.priority_sim_test'
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()

    truth = {}  # id -> content
    next_id = 0
    stats = {'add': 0, 'delete': 0, 'rerank': 0, 'list': 0, 'normalize': 0}
    times = {'add': [], 'delete': [], 'rerank': [], 'list': []}
    errors = []

    start = time.time()
    ops = 0

    while time.time() - start < duration:
        op = random.choices(['add', 'delete', 'rerank', 'list', 'normalize'], weights=[40, 15, 30, 10, 5])[0]

        try:
            if op == 'add':
                content = f'task-{next_id}-' + ''.join(random.choices(string.ascii_lowercase, k=10))
                pri = f'{random.randint(0, 999):03d}'
                t0 = time.perf_counter_ns()
                add(d, content, pri)
                times['add'].append(time.perf_counter_ns() - t0)
                truth[next_id] = content
                next_id += 1

            elif op == 'delete' and truth:
                files = ls(d)
                if files:
                    f = random.choice(files)
                    content = f.read_text().strip()
                    tid = int(content.split('-')[1])
                    t0 = time.perf_counter_ns()
                    delete(f)
                    times['delete'].append(time.perf_counter_ns() - t0)
                    del truth[tid]

            elif op == 'rerank' and truth:
                files = ls(d)
                if files:
                    f = random.choice(files)
                    new_pri = f'{random.randint(0, 999):03d}'
                    t0 = time.perf_counter_ns()
                    rerank(f, new_pri)
                    times['rerank'].append(time.perf_counter_ns() - t0)

            elif op == 'list':
                t0 = time.perf_counter_ns()
                ls(d)
                times['list'].append(time.perf_counter_ns() - t0)

            elif op == 'normalize':
                if random.random() < 0.3:
                    content = f'manual-{next_id}'
                    (d / f'manual_{next_id}.txt').write_text(content + '\n')
                    truth[next_id] = content
                    next_id += 1
                normalize(d)

            stats[op] += 1
            ops += 1

        except Exception as e:
            errors.append(f'{op}: {e}')

    # === VERIFY NO DATA LOSS ===
    files = ls(d)
    file_contents = {f.read_text().strip() for f in files}
    truth_contents = set(truth.values())
    lost = truth_contents - file_contents
    extra = file_contents - truth_contents

    # === RESULTS ===
    print(f'=== Monte Carlo Priority Sim ({duration}s) ===\n')
    print(f'Operations: {ops:,} total')
    for k, v in stats.items():
        print(f'  {k}: {v:,}')

    print(f'\n=== Performance (microseconds) ===')
    # Realistic targets for file I/O on mobile
    targets = {'add': 200, 'delete': 200, 'rerank': 100, 'list': 50000}  # microseconds
    all_pass = True
    for op, t in times.items():
        if t:
            t_us = [x / 1000 for x in t]  # convert to microseconds
            avg = sum(t_us) / len(t_us)
            p99 = sorted(t_us)[int(len(t_us) * 0.99)] if len(t_us) > 100 else max(t_us)
            target = targets.get(op, 10000)
            status = '✓' if avg < target else '✗'
            if avg >= target:
                all_pass = False
            print(f'  {op}: avg={avg:.1f}us p99={p99:.1f}us target={target}us {status}')

    print(f'\n=== Data Integrity ===')
    print(f'  Tasks tracked: {len(truth)}')
    print(f'  Files on disk: {len(files)}')
    print(f'  Lost: {len(lost)} {"✗" if lost else "✓"}')
    print(f'  Extra: {len(extra)} {"✗" if extra else "✓"}')

    if errors:
        print(f'\n=== Errors ({len(errors)}) ===')
        for e in errors[:5]:
            print(f'  {e}')

    # Cleanup
    shutil.rmtree(d)

    ok = len(lost) == 0 and len(extra) == 0 and not errors
    print(f'\n{"PASS" if ok else "FAIL"} (data integrity: {"✓" if ok else "✗"}, perf: {"✓" if all_pass else "✗"})')
    return ok

if __name__ == '__main__':
    import sys
    ok = run_sim(duration=10)
    sys.exit(0 if ok else 1)
