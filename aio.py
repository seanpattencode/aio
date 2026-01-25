#!/usr/bin/env python3
"""aio - AI agent session manager (git-like modular dispatcher)"""
import sys, os

# Fast-path for 'aio n <text>' - append-only event + sqlite insert
# SYNC: Emits notes.add event to events.jsonl. Never delete - ack to archive. Any device can ack.
if len(sys.argv) > 2 and sys.argv[1] in ('note', 'n') and sys.argv[2][0] != '?':
    import sqlite3, subprocess as sp, json, time, hashlib, socket; dd = os.path.expanduser("~/.local/share/aios"); db = f"{dd}/aio.db"; ef = f"{dd}/events.jsonl"; os.makedirs(dd, exist_ok=True); dev = (sp.run(['getprop','ro.product.model'],capture_output=True,text=True).stdout.strip().replace(' ','-') or socket.gethostname()) if os.path.exists('/data/data/com.termux') else socket.gethostname()
    eid = hashlib.md5(f"{time.time()}{os.getpid()}".encode()).hexdigest()[:8]; txt = ' '.join(sys.argv[2:]); ev = json.dumps({"ts": time.time(), "id": eid, "dev": dev, "op": "notes.add", "d": {"t": txt}})
    open(ef, "a").write(ev + "\n"); c = sqlite3.connect(db); c.execute("CREATE TABLE IF NOT EXISTS notes(id,t,s DEFAULT 0,d,c DEFAULT CURRENT_TIMESTAMP,proj)"); c.execute("INSERT OR REPLACE INTO notes(id,t,s) VALUES(?,?,0)", (eid, txt)); c.commit(); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.close()
    sp.run(f'cd "{dd}" && git add -A && git diff --cached --quiet || git -c user.name=aio -c user.email=a@a commit -m n -q; git fetch -q && git -c user.name=aio -c user.email=a@a merge -q -X theirs --no-edit origin/main 2>/dev/null', shell=True, capture_output=True) if os.path.isdir(f"{dd}/.git") else None
    eid not in open(ef).read() and open(ef, "a").write(ev + "\n"); r = sp.run(f'cd "{dd}" && git add -A && git diff --cached --quiet || git -c user.name=aio -c user.email=a@a commit -m n -q; git push origin HEAD:main -q', shell=True, capture_output=True, text=True) if os.path.isdir(f"{dd}/.git") else type('R',(),{'returncode':0})(); print("✓" if r.returncode == 0 else f"! {r.stderr.strip()[:40] or 'sync failed'}"); sys.exit(0)

# Fast-path for 'aio i' - show cache instantly, start interactive in background
# NOTE: Agents test with `bash -i -c 'aio i'`, time with `bash -i -c 'time aio i < /dev/null' 2>&1`
if len(sys.argv) > 1 and sys.argv[1] == 'i':
    c = os.path.expanduser("~/.local/share/aios/i_cache.txt")
    if not sys.stdin.isatty(): print(open(c).read() if os.path.exists(c) else '', end=''); sys.exit(0)
    if not os.environ.get('_AIO_I'): items = (open(c).read().strip().split('\n')[:8]+['']*8)[:8] if os.path.exists(c) else ['']*8; print("Type to filter, Tab=cycle, Enter=run, Esc=quit\n\n> \033[s\n > "+items[0]+'\n'+'\n'.join(f"   {m}" for m in items[1:]))

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
    'add': 'add', 'remove': 'remove', 'rem': 'remove', 'rm': 'remove', 'move': 'move', 'mov': 'move', 'dash': 'dash', 'das': 'dash',
    'all': 'multi', 'backup': 'backup', 'bak': 'backup', 'scan': 'scan', 'sca': 'scan',
    'e': 'e', 'x': 'x', 'p': 'p', 'copy': 'copy', 'cop': 'copy', 'log': 'log', 'done': 'done',
    'agent': 'agent', 'tree': 'tree', 'tre': 'tree', 'dir': 'dir', 'web': 'web', 'ssh': 'ssh', 'run': 'run', 'hub': 'hub',
    'daemon': 'daemon', 'ui': 'ui', 'review': 'review', 'n': 'note', 'note': 'note', 'i': 'i',
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
