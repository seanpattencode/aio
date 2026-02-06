# Append-only tasks: folders with text_*.txt candidates + prompt_*.txt
# Uses sync.py append-only logic for conflict-free sync
# Bash TUI: a_cmd/task/t (fast interactive review, 5ms startup)

import sys, os, shutil
from pathlib import Path
from .._common import SYNC_ROOT, DEVICE_ID
from ..sync import _sync, ts

TASK_DIR = SYNC_ROOT / 'tasks'
T_SCRIPT = Path(__file__).parent / 't'

def _tasks():
    """Get all tasks: folders and legacy .txt files, sorted by timestamp"""
    items = []
    for p in TASK_DIR.iterdir():
        if p.name.startswith('.'): continue
        if p.is_dir():
            latest = max(p.glob('text_*.txt'), default=None, key=lambda f: f.name)
            if latest: items.append((p, latest.read_text().strip().split('\n')[0]))
        elif p.suffix == '.txt':
            items.append((p, p.read_text().strip().split('\n')[0]))
    return sorted(items, key=lambda x: x[0].name)

def _slug(text):
    s = text[:20].replace(' ', '-').replace('/', '-').lower()
    return ''.join(c for c in s if c.isalnum() or c == '-')

def run():
    TASK_DIR.mkdir(exist_ok=True)
    a = sys.argv[2:]

    if not a:
        print(f"""a task l        list all tasks
a task add <t>  add a task (creates folder with text candidate)
a task d #      archive task by number
a task t        interactive review (bash TUI)
a task sync     sync tasks repo
a task 0        AI pick top priority
a task 1        AI session: analyze & help (~/a-sync/common/prompts/task1.txt)
a task p        AI plan each
a task do       AI do tasks
a task s        AI suggest

context: ~/a-sync/tasks/
https://github.com/seanpattencode/a-git""")
        return

    cmd = a[0]
    tasks = _tasks()

    # List tasks
    if cmd in ('l', 'ls', 'list'):
        if not tasks:
            print("No tasks"); return
        for i, (p, text) in enumerate(tasks, 1):
            tag = 'd' if p.is_dir() else 'f'
            print(f"{i}. [{tag}] {text[:60]}")
        return

    # Add task (creates folder with text candidate)
    if cmd in ('add', 'a') or (cmd not in ('d', 'del', 'delete', 'sync', 'l', 'ls', 'list', '0', '1', 'p', 'do', 's', 't', 'h', '--help', '-h')):
        text = ' '.join(a[1:]) if cmd in ('add', 'a') else ' '.join(a)
        if not text:
            print("Usage: a task add <task description>"); return
        folder = TASK_DIR / f'{_slug(text)}_{ts()}'
        folder.mkdir()
        (folder / f'text_{ts()}_{DEVICE_ID}.txt').write_text(text + '\n')
        print(f"✓ Added: {text}")
        _sync(silent=True)
        return

    # Archive task
    if cmd in ('d', 'del', 'delete'):
        if len(a) < 2:
            print("Usage: a task d <number>"); return
        try:
            idx = int(a[1]) - 1
            if 0 <= idx < len(tasks):
                p, text = tasks[idx]
                arc = TASK_DIR / '.archive'; arc.mkdir(exist_ok=True)
                shutil.move(str(p), str(arc / p.name))
                print(f"✓ Archived: {text[:40]}")
                _sync(silent=True)
            else:
                print(f"Invalid task number: {a[1]}")
        except ValueError:
            print(f"Invalid number: {a[1]}")
        return

    # Sync
    if cmd == 'sync':
        ok, conflict = _sync()
        print("✓ Tasks synced" if ok else ("" if conflict else "✓ No changes"))
        return

    # AI commands
    if cmd in ('0', 'p', 'do', 's'):
        import subprocess
        subprocess.run(['a', 'x.' + {'0': 'priority', 'p': 'plan', 'do': 'do', 's': 'suggest'}[cmd]])
        return

    # AI session with task prompt
    if cmd == '1':
        pf = SYNC_ROOT / 'common' / 'prompts' / 'task1.txt'
        if not pf.exists():
            print(f"x No prompt: {pf}"); return
        print(f"Prompt: {pf}")
        os.execvp('a', ['a', 'c', pf.read_text().strip()])
        return

    # Interactive review (bash TUI)
    if cmd in ('t', '--time', '-h', '--help', 'h'):
        os.execvp('bash', ['bash', str(T_SCRIPT)] + a[1:])

    print(f"Unknown command: {cmd}")
