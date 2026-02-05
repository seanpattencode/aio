# Append-only tasks: {name}_{timestamp}.txt = no conflicts
# Uses sync.py append-only logic for conflict-free sync

import sys, time
from pathlib import Path
from ._common import SYNC_ROOT, DEVICE_ID
from .sync import _sync, ts, get_latest, add_timestamps

def run():
    d = SYNC_ROOT / 'tasks'
    d.mkdir(exist_ok=True)
    a = sys.argv[2:]

    # Get all task files sorted by timestamp in filename (not mtime)
    tasks = sorted([f for f in d.glob('*.txt') if '_20' in f.stem or not f.name.startswith('.')],
                   key=lambda f: f.stem.rsplit('_', 1)[-1] if '_20' in f.stem else '0')

    if not a:
        print("""a task l        list all tasks
a task add <t>  add a task
a task d #      delete task by number
a task sync     sync tasks repo
a task 0        AI pick top priority
a task p        AI plan each
a task do       AI do tasks
a task s        AI suggest

context: ~/a-sync/tasks/
https://github.com/seanpattencode/a-git""")
        return

    cmd = a[0]

    # List tasks
    if cmd in ('l', 'ls', 'list'):
        if not tasks:
            print("No tasks")
            return
        for i, f in enumerate(tasks, 1):
            content = f.read_text().strip().split('\n')[0][:60]
            print(f"{i}. {content}")
        return

    # Add task
    if cmd in ('add', 'a') or (cmd not in ('d', 'del', 'delete', 'sync', 'l', 'ls', 'list', '0', 'p', 'do', 's', 't', 'h', '--help', '-h')):
        text = ' '.join(a[1:]) if cmd in ('add', 'a') else ' '.join(a)
        if not text:
            print("Usage: a task add <task description>")
            return
        # Create filename: first 20 chars slugified + timestamp
        slug = text[:20].replace(' ', '-').replace('/', '-').lower()
        slug = ''.join(c for c in slug if c.isalnum() or c == '-')
        filename = f'{slug}_{ts()}.txt'
        (d / filename).write_text(text + '\n')
        print(f"✓ Added: {text}")
        _sync(silent=True)
        return

    # Delete task
    if cmd in ('d', 'del', 'delete'):
        if len(a) < 2:
            print("Usage: a task d <number>")
            return
        try:
            idx = int(a[1]) - 1
            if 0 <= idx < len(tasks):
                f = tasks[idx]
                content = f.read_text().strip().split('\n')[0][:40]
                f.unlink()
                print(f"✓ Deleted: {content}")
                _sync(silent=True)
            else:
                print(f"Invalid task number: {a[1]}")
        except ValueError:
            print(f"Invalid number: {a[1]}")
        return

    # Sync
    if cmd == 'sync':
        add_timestamps(d)
        ok, conflict = _sync()
        if ok:
            print("✓ Tasks synced")
        elif conflict:
            pass  # _sync already printed conflict message
        else:
            print("✓ Tasks synced (no changes)")
        return

    # AI commands
    if cmd in ('0', 'p', 'do', 's'):
        import subprocess
        subprocess.run(['a', 'x.' + {'0': 'priority', 'p': 'plan', 'do': 'do', 's': 'suggest'}[cmd]])
        return

    # Help / passthrough to t command
    if cmd in ('t', '--time', '-h', '--help', 'h'):
        import os
        os.execlp('t', 't', *(a[1:] if cmd == 't' else a))

    print(f"Unknown command: {cmd}")
