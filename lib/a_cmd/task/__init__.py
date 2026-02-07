# Append-only tasks: PPPP-slug_timestamp/ with subdirs: task/, context/, prompt/
# 4-letter priority ordinal (A=high Z=low, default MMMM)
# Subfolders are generic - any name works, 3 created by default
# Bash TUI: a_cmd/task/t

import sys, os, shutil
from pathlib import Path
from .._common import SYNC_ROOT, DEVICE_ID
from ..sync import _sync, ts

TASK_DIR = SYNC_ROOT / 'tasks'
T_SCRIPT = Path(__file__).parent / 't'
SUBDIRS = ('task', 'context', 'prompt')

def _pri(name):
    return name[:4].upper() if len(name) > 4 and name[4] == '-' and name[:4].isalpha() else 'MMMM'

def _first_line(f):
    t = f.read_text().strip().split('\n')[0]
    return t[6:] if t.startswith('Text: ') else t

def _task_text(p):
    if p.is_dir():
        td = p / 'task'
        if td.is_dir():
            g = sorted(td.glob('*.txt'), reverse=True)
            if g: return _first_line(g[0])
        g = sorted(p.glob('text_*.txt'), reverse=True)
        if g: return _first_line(g[0])
    elif p.suffix == '.txt':
        return _first_line(p)
    return None

def _tasks():
    items = []
    for p in TASK_DIR.iterdir():
        if p.name.startswith('.') or p.name == 'README.md': continue
        t = _task_text(p)
        if t: items.append((p, t, _pri(p.name)))
    return sorted(items, key=lambda x: (x[2], x[0].name))

def _slug(text):
    s = text[:20].replace(' ', '-').replace('/', '-').lower()
    return ''.join(c for c in s if c.isalnum() or c == '-')

def _counts(p):
    if not p.is_dir(): return ''
    parts = []
    for sd in sorted(p.iterdir()):
        if sd.is_dir() and not sd.name.startswith('.'):
            n = sum(1 for f in sd.iterdir() if f.is_file())
            if n: parts.append(f'{n} {sd.name}')
    for pre in ['text_', 'prompt_']:
        n = len(list(p.glob(f'{pre}*.txt')))
        if n: parts.append(f'{n} {pre.rstrip("_")}')
    return f' [{", ".join(parts)}]' if parts else ''

def run():
    TASK_DIR.mkdir(exist_ok=True)
    a = sys.argv[2:]

    if not a:
        print("""a task l            list all tasks
a task add <t>      add task (MMMM default priority)
a task d #          archive task by number
a task pri # XXXX   change priority (4 letters, A=high Z=low)
a task <cat> # <t>  add to subfolder (context, prompt, or any)
a task t            interactive review (bash TUI)
a task sync         sync tasks repo
a task 0|1|p|do|s   AI commands

context: ~/projects/adata/git/tasks/""")
        return

    cmd = a[0]
    tasks = _tasks()

    if cmd in ('l', 'ls', 'list'):
        if not tasks: print("No tasks"); return
        for i, (p, text, pri) in enumerate(tasks, 1):
            print(f"{i}. {pri} {text[:55]}{_counts(p)}")
        return

    if cmd == 'pri':
        if len(a) < 3: print("Usage: a task pri <#> <XXXX>"); return
        try:
            idx, np = int(a[1]) - 1, a[2].upper()[:4].ljust(4, a[2][-1].upper())
            if not np.isalpha(): print("Letters only"); return
            if 0 <= idx < len(tasks):
                p, text, _ = tasks[idx]
                old = p.name
                new = np + '-' + (old[5:] if _pri(old) != 'MMMM' or (len(old) > 4 and old[4] == '-' and old[:4].isalpha()) else old)
                p.rename(TASK_DIR / new)
                print(f"\u2713 {np} {text[:40]}")
                _sync(silent=True)
            else: print(f"Invalid: {a[1]}")
        except ValueError: print(f"Invalid: {a[1]}")
        return

    # Generic subfolder add: a task <cat> <#> <text>
    if len(a) >= 3 and a[1].isdigit() and cmd not in ('add', 'a', 'd', 'del', 'delete', 'sync', '0', '1', 'p', 'do', 's', 't', 'h', 'pri'):
        try:
            idx, text = int(a[1]) - 1, ' '.join(a[2:])
            if 0 <= idx < len(tasks):
                p = tasks[idx][0]
                if not p.is_dir(): print("x Not a folder task"); return
                sd = p / cmd; sd.mkdir(exist_ok=True)
                (sd / f'{ts()}_{DEVICE_ID}.txt').write_text(text + '\n')
                print(f"\u2713 {cmd}: {text[:40]}")
                _sync(silent=True)
            else: print(f"Invalid: {a[1]}")
        except ValueError: print(f"Invalid: {a[1]}")
        return

    if cmd in ('add', 'a') or cmd not in ('d', 'del', 'delete', 'sync', 'l', 'ls', 'list', '0', '1', 'p', 'do', 's', 't', 'h', '--help', '-h', 'pri'):
        text = ' '.join(a[1:]) if cmd in ('add', 'a') else ' '.join(a)
        if not text: print("Usage: a task add <text>"); return
        folder = TASK_DIR / f'MMMM-{_slug(text)}_{ts()}'
        folder.mkdir()
        for sd in SUBDIRS: (folder / sd).mkdir()
        (folder / 'task' / f'{ts()}_{DEVICE_ID}.txt').write_text(text + '\n')
        print(f"\u2713 MMMM {text}")
        _sync(silent=True)
        return

    if cmd in ('d', 'del', 'delete'):
        if len(a) < 2: print("Usage: a task d <#>"); return
        try:
            idx = int(a[1]) - 1
            if 0 <= idx < len(tasks):
                p, text, _ = tasks[idx]
                arc = TASK_DIR / '.archive'; arc.mkdir(exist_ok=True)
                shutil.move(str(p), str(arc / p.name))
                print(f"\u2713 Archived: {text[:40]}")
                _sync(silent=True)
            else: print(f"Invalid: {a[1]}")
        except ValueError: print(f"Invalid: {a[1]}")
        return

    if cmd == 'sync':
        ok, conflict = _sync()
        print("\u2713 Tasks synced" if ok else ("" if conflict else "\u2713 No changes"))
        return

    if cmd in ('0', 'p', 'do', 's'):
        import subprocess
        subprocess.run(['a', 'x.' + {'0': 'priority', 'p': 'plan', 'do': 'do', 's': 'suggest'}[cmd]])
        return

    if cmd == '1':
        pf = SYNC_ROOT / 'common' / 'prompts' / 'task1.txt'
        if not pf.exists(): print(f"x No prompt: {pf}"); return
        print(f"Prompt: {pf}")
        os.execvp('a', ['a', 'c', pf.read_text().strip()])
        return

    if cmd in ('t', '--time', '-h', '--help', 'h'):
        os.execvp('bash', ['bash', str(T_SCRIPT)] + a[1:])

    print(f"Unknown command: {cmd}")
