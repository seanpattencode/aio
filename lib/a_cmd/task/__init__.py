# Append-only tasks: NNNNN-slug_timestamp/ with subdirs: task/, context/, prompt/
# 5-digit priority (00001=high, 99999=low, default 50000)
# Subfolders are generic - any name works, 3 created by default
# Bash TUI: a_cmd/task/t

import sys, os, shutil
from pathlib import Path
from .._common import SYNC_ROOT, DEVICE_ID
from ..sync import _sync, ts

TASK_DIR = SYNC_ROOT / 'tasks'
T_SCRIPT = Path(__file__).parent / 't'
SUBDIRS = ('task', 'context', 'prompt')
DEF_PRI = '50000'

def _pri(name):
    return name[:5] if len(name) > 5 and name[5] == '-' and name[:5].isdigit() else DEF_PRI

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

def _fmtpri(s):
    """Normalize priority input to 5-digit zero-padded string"""
    try:
        n = max(0, min(99999, int(s)))
        return f'{n:05d}'
    except ValueError: return None

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

def _rename_pri(p, np):
    old = p.name
    rest = old[6:] if len(old) > 5 and old[5] == '-' and old[:5].isdigit() else old
    p.rename(TASK_DIR / f'{np}-{rest}')

def _show_task(p, text, pri, idx, total):
    print(f"\n\033[1m━━━ {idx}/{total} [P{pri}] {text[:60]} ━━━\033[0m")
    if p.is_dir():
        for sd in sorted(p.iterdir()):
            if sd.is_dir() and not sd.name.startswith('.'):
                files = sorted(sd.glob('*.txt'))
                if not files: continue
                print(f"\n  \033[36m{sd.name}/\033[0m ({len(files)})")
                for f in files:
                    body = f.read_text().strip()
                    if body.startswith('Text: '): body = body[6:]
                    for line in body.split('\n'):
                        print(f"    {line}")
        for f in sorted(p.glob('text_*.txt')) + sorted(p.glob('prompt_*.txt')):
            body = f.read_text().strip()
            if body.startswith('Text: '): body = body[6:]
            print(f"\n  \033[33m{f.name}\033[0m")
            for line in body.split('\n'):
                print(f"    {line}")
    else:
        print(f"\n  {p.read_text().strip()}")

def _getkey():
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try: tty.setraw(fd); return sys.stdin.read(1)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)

def run():
    TASK_DIR.mkdir(exist_ok=True)
    a = sys.argv[2:]

    if not a:
        print("""a task l            list all tasks
a task rev          review tasks by priority (full detail)
a task add <t>      add task (default priority 50000)
a task d #          archive task by number
a task pri # N      set priority (1=high, 99999=low)
a task <cat> # <t>  add to subfolder (context, prompt, or any)
a task t            interactive TUI (bash)
a task sync         sync tasks repo
a task 0|1|p|do|s   AI commands

context: ~/projects/adata/git/tasks/""")
        return

    cmd = a[0]
    tasks = _tasks()

    if cmd in ('l', 'ls', 'list'):
        if not tasks: print("No tasks"); return
        for i, (p, text, pri) in enumerate(tasks, 1):
            print(f"{i}. P{pri} {text[:55]}{_counts(p)}")
        return

    if cmd in ('rev', 'review'):
        if not tasks: print("No tasks"); return
        i = 0
        while i < len(tasks):
            p, text, pri = tasks[i]
            _show_task(p, text, pri, i + 1, len(tasks))
            print(f"\n  [d]archive  [n]ext  [p]ri  [q]uit  ", end='', flush=True)
            k = _getkey(); print()
            if k == 'd':
                arc = TASK_DIR / '.archive'; arc.mkdir(exist_ok=True)
                shutil.move(str(p), str(arc / p.name))
                print(f"\u2713 Archived: {text[:40]}")
                tasks.pop(i); _sync(silent=True)
            elif k == 'p':
                print("  Priority (1-99999): ", end='', flush=True)
                np = _fmtpri(input().strip())
                if np:
                    _rename_pri(p, np)
                    print(f"\u2713 P{np}"); _sync(silent=True)
                    tasks = _tasks(); i = 0
                else: print("x Invalid number")
            elif k in ('q', '\x03', '\x1b'): break
            else: i += 1
        print("Done" if i >= len(tasks) else "")
        return

    if cmd == 'pri':
        if len(a) < 3: print("Usage: a task pri <#> <priority>"); return
        try:
            idx = int(a[1]) - 1
            np = _fmtpri(a[2])
            if not np: print("Invalid number"); return
            if 0 <= idx < len(tasks):
                p, text, _ = tasks[idx]
                _rename_pri(p, np)
                print(f"\u2713 P{np} {text[:40]}")
                _sync(silent=True)
            else: print(f"Invalid: {a[1]}")
        except ValueError: print(f"Invalid: {a[1]}")
        return

    # Generic subfolder add: a task <cat> <#> <text>
    if len(a) >= 3 and a[1].isdigit() and cmd not in ('add', 'a', 'd', 'del', 'delete', 'sync', '0', '1', 'p', 'do', 's', 't', 'h', 'pri', 'rev', 'review'):
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

    if cmd in ('add', 'a') or cmd not in ('d', 'del', 'delete', 'sync', 'l', 'ls', 'list', '0', '1', 'p', 'do', 's', 't', 'h', '--help', '-h', 'pri', 'rev', 'review'):
        text = ' '.join(a[1:]) if cmd in ('add', 'a') else ' '.join(a)
        if not text: print("Usage: a task add <text>"); return
        folder = TASK_DIR / f'{DEF_PRI}-{_slug(text)}_{ts()}'
        folder.mkdir()
        for sd in SUBDIRS: (folder / sd).mkdir()
        (folder / 'task' / f'{ts()}_{DEVICE_ID}.txt').write_text(text + '\n')
        print(f"\u2713 P{DEF_PRI} {text}")
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
