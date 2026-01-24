#!/usr/bin/env python3
"""aio - AI agent session manager (git-like modular dispatcher)"""
import sys, os

# Fast-path for 'aio n <text>' - no imports needed
if len(sys.argv) > 2 and sys.argv[1] in ('note', 'n'):
    import sqlite3, subprocess as sp; dd = os.path.expanduser("~/.local/share/aios"); db = f"{dd}/aio.db"; os.makedirs(dd, exist_ok=True); os.path.exists(db) and sqlite3.connect(db).execute("PRAGMA wal_checkpoint(TRUNCATE)").connection.close(); (os.path.isdir(f"{dd}/.git") or __import__('shutil').which('gh') and (u:=sp.run(['gh','repo','view','aio-sync','--json','url','-q','.url'],capture_output=True,text=True).stdout.strip() or sp.run(['gh','repo','create','aio-sync','--private','-y'],capture_output=True,text=True).stdout.strip()) and sp.run(f'cd "{dd}"&&git init -b main -q;git remote add origin {u} 2>/dev/null;git fetch origin 2>/dev/null&&git reset --hard origin/main 2>/dev/null||(git add -A&&git commit -m init -q&&git push -u origin main 2>/dev/null)',shell=True,capture_output=True)) and sp.run(f'cd "{dd}" && git fetch -q 2>/dev/null && git reset --hard origin/main 2>/dev/null', shell=True, capture_output=True); c = sqlite3.connect(db); c.execute("CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,t,s DEFAULT 0,d,c DEFAULT CURRENT_TIMESTAMP,proj)"); c.execute("INSERT INTO notes(t) VALUES(?)", (' '.join(sys.argv[2:]),)); c.commit(); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.close(); r = sp.run(f'cd "{dd}" && git add -A && git diff --cached --quiet || git -c user.name=aio -c user.email=a@a commit -m n && git push origin HEAD:main -q 2>&1', shell=True, capture_output=True, text=True) if os.path.isdir(f"{dd}/.git") else type('R',(),{'returncode':0})(); print("✓" if r.returncode == 0 else f"! {r.stderr.strip()[:40] or 'sync failed'}"); sys.exit(0)

# Generate monolith from all modules
if len(sys.argv) > 1 and sys.argv[1] in ('mono', 'monolith'):
    p = os.path.expanduser("~/.local/share/aios/aio_mono.py"); open(p, 'w').write('\n\n'.join(f"# === {f} ===\n" + open(f).read() for f in sorted(__import__('glob').glob(os.path.dirname(__file__) + '/aio_cmd/*.py')))); print(p); sys.exit(0)

# Command dispatch table (like git's cmd_struct)
CMDS = {
    None: 'help', '': 'help', 'help': 'help_full', 'hel': 'help_full', '--help': 'help_full', '-h': 'help_full',
    'update': 'update', 'upd': 'update', 'jobs': 'jobs', 'job': 'jobs', 'kill': 'kill', 'kil': 'kill', 'killall': 'kill',
    'attach': 'attach', 'att': 'attach', 'cleanup': 'cleanup', 'cle': 'cleanup', 'config': 'config', 'con': 'config',
    'ls': 'ls', 'diff': 'diff', 'dif': 'diff', 'send': 'send', 'sen': 'send', 'watch': 'watch', 'wat': 'watch',
    'push': 'push', 'pus': 'push', 'pull': 'pull', 'pul': 'pull', 'revert': 'revert', 'rev': 'revert',
    'set': 'set', 'settings': 'set', 'install': 'install', 'ins': 'install', 'uninstall': 'uninstall', 'uni': 'uninstall',
    'deps': 'deps', 'dep': 'deps', 'prompt': 'prompt', 'pro': 'prompt', 'gdrive': 'gdrive', 'gdr': 'gdrive',
    'add': 'add', 'remove': 'remove', 'rem': 'remove', 'rm': 'remove', 'dash': 'dash', 'das': 'dash',
    'all': 'multi', 'backup': 'backup', 'bak': 'backup', 'scan': 'scan', 'sca': 'scan',
    'e': 'e', 'x': 'x', 'p': 'p', 'copy': 'copy', 'cop': 'copy', 'log': 'log', 'done': 'done',
    'agent': 'agent', 'tree': 'tree', 'tre': 'tree', 'dir': 'dir', 'web': 'web', 'ssh': 'ssh', 'run': 'run', 'hub': 'hub',
    'daemon': 'daemon', 'ui': 'ui', 'review': 'review',
}

def main():
    import time; _START = time.time()
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    wda = sys.argv[2] if len(sys.argv) > 2 else None

    # Timing
    import atexit, json
    from datetime import datetime
    _CMD = ' '.join(sys.argv[1:3]) if len(sys.argv) > 1 else 'help'
    def _save_timing():
        try: d = os.path.expanduser("~/.local/share/aios"); os.makedirs(d, exist_ok=True); open(f"{d}/timing.jsonl", "a").write(json.dumps({"cmd": _CMD, "ms": int((time.time() - _START) * 1000), "ts": datetime.now().isoformat()}) + "\n")
        except: pass
    atexit.register(_save_timing)

    # Check for known command
    cmd_name = CMDS.get(arg)

    if cmd_name:
        # Lazy import command module
        mod = __import__(f'aio_cmd.{cmd_name}', fromlist=[cmd_name])
        mod.run()
    elif arg and arg.endswith('++') and not arg.startswith('w'):
        # Worktree++ command
        from aio_cmd import wt_plus; wt_plus.run()
    elif arg and arg.startswith('w') and arg not in ('watch', 'web') and not os.path.isfile(arg):
        # Worktree command
        from aio_cmd import wt; wt.run()
    elif arg and (os.path.isdir(os.path.expanduser(arg)) or os.path.isfile(arg) or (arg.startswith('/projects/') and os.path.isdir(os.path.expanduser('~' + arg)))):
        # Directory/file command
        from aio_cmd import dir_file; dir_file.run()
    elif arg and arg.isdigit():
        # Project number shortcut
        from aio_cmd import project_num; project_num.run()
    else:
        # Session command (fallback)
        from aio_cmd import sess; sess.run()

if __name__ == '__main__':
    main()
