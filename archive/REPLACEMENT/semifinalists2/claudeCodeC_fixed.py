#!/usr/bin/env python3
"""claudeCodeC Fixed: Perfect Minimalism with Systemd Integration"""
import sqlite3, subprocess, json, time, sys, os, signal
from pathlib import Path

UNIT_PREFIX = "aios-"

class S:
    """Systemd wrapper for oneshot tasks"""
    def _run(self, *args):
        return subprocess.run(["systemctl", "--user"] + list(args),
                              capture_output=True, text=True, check=False)

    def add_oneshot(self, name, cmd):
        unit = f"{UNIT_PREFIX}{name}.service"
        path = Path(f"~/.config/systemd/user/{unit}").expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"""[Unit]
Description=Task: {name}
[Service]
Type=oneshot
ExecStart=/bin/sh -c '{cmd}'
StandardOutput=journal
StandardError=journal
""")
        self._run("daemon-reload")
        return unit

    def start(self, unit):
        self._run("start", unit)

    def status(self, unit):
        res = self._run("show", unit, "--property=ActiveState,Result")
        props = {}
        for line in res.stdout.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                props[k] = v
        return props.get('ActiveState', 'unknown'), props.get('Result', 'unknown')

    def remove(self, unit):
        self._run("stop", unit)
        path = Path(f"~/.config/systemd/user/{unit}").expanduser()
        if path.exists():
            path.unlink()
        self._run("daemon-reload")

class Q:
    """The Essential Queue - Nothing More"""
    def __init__(self, db="tasks.db"):
        self.c = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
        for sql in [
            "PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL", "PRAGMA temp_store=MEMORY",
            "PRAGMA mmap_size=268435456", "PRAGMA cache_size=-64000", "PRAGMA busy_timeout=5000",
            """CREATE TABLE IF NOT EXISTS t (
                id INTEGER PRIMARY KEY, name TEXT, cmd TEXT, p INT DEFAULT 0,
                s TEXT DEFAULT 'q', at INT DEFAULT 0, w TEXT, r INT DEFAULT 0
            )""",
            "CREATE INDEX IF NOT EXISTS i ON t(s,p DESC,at) WHERE s='q'"
        ]: self.c.execute(sql)

    def add(self, name, cmd, p=0, at=None):
        """Add task"""
        return self.c.execute("INSERT INTO t(name,cmd,p,at) VALUES(?,?,?,?)",
                              (name, cmd, p, at or int(time.time()*1000))).lastrowid

    def pop(self):
        """Get next task atomically"""
        r = self.c.execute("""
            UPDATE t SET s='r', w=? WHERE id=(
                SELECT id FROM t WHERE s='q' AND at<=?
                ORDER BY p DESC, at LIMIT 1
            ) RETURNING id, name, cmd
        """, (str(os.getpid()), int(time.time()*1000))).fetchone()
        return {'id': r[0], 'name': r[1], 'cmd': r[2]} if r else None

    def done(self, id, ok=True):
        """Complete or retry task"""
        if ok:
            self.c.execute("UPDATE t SET s='d' WHERE id=?", (id,))
        else:
            r = self.c.execute("SELECT r FROM t WHERE id=?", (id,)).fetchone()
            if r and r[0] < 3:
                self.c.execute("UPDATE t SET s='q',r=r+1,at=? WHERE id=?",
                               (int(time.time()*1000) + 1000*(2**r[0]), id))
            else:
                self.c.execute("UPDATE t SET s='f' WHERE id=?", (id,))

    def reclaim_dead(self):
        """Reclaim tasks from dead workers"""
        cursor = self.c.execute("SELECT DISTINCT w FROM t WHERE s='r' AND w IS NOT NULL")
        for (w,) in cursor.fetchall():
            try:
                os.kill(int(w), 0)
            except (OSError, ValueError):
                self.c.execute("UPDATE t SET s='q', w=NULL, r=r+1 WHERE w=?", (w,))

    def stats(self):
        """Get counts"""
        return {r[0]: r[1] for r in self.c.execute("SELECT s,COUNT(*) FROM t GROUP BY s")}

def worker(q=None, batch=1):
    """Process tasks via systemd oneshots"""
    q = q or Q()
    s = S()
    flag = [True]
    signal.signal(signal.SIGTERM, lambda *_: flag.__setitem__(0, False))
    signal.signal(signal.SIGINT, lambda *_: flag.__setitem__(0, False))

    while flag[0]:
        tasks = [q.pop() for _ in range(batch)]
        tasks = [t for t in tasks if t]
        if tasks:
            units = {}
            for t in tasks:
                unit = s.add_oneshot(t['name'], t['cmd'])
                s.start(unit)
                units[t['id']] = unit
            while units:
                for tid, unit in list(units.items()):
                    state, result = s.status(unit)
                    if state in ('inactive', 'failed'):
                        ok = state == 'inactive' and result == 'success'
                        q.done(tid, ok)
                        s.remove(unit)
                        del units[tid]
                if units:
                    time.sleep(0.5)
        else:
            q.reclaim_dead()
            time.sleep(0.05)

def bench():
    """Benchmark"""
    db = "bench.db"
    if os.path.exists(db): os.unlink(db)
    q = Q(db)

    # Insert test
    s = time.perf_counter()
    for i in range(1000):
        q.add(f"task{i}", f"echo {i}", i%10)
    t1 = (time.perf_counter()-s)*1000

    # Pop test
    s = time.perf_counter()
    for _ in range(100):
        q.pop()
    t2 = (time.perf_counter()-s)*1000

    print(f"""claudeCodeC Fixed Benchmark:
1000 inserts: {t1:.2f}ms ({t1/1000:.4f}ms per op)
100 pops: {t2:.2f}ms ({t2/100:.4f}ms per op)""")

def systemd():
    """Generate systemd unit for worker"""
    return f"""[Unit]
Description=Task Worker
[Service]
ExecStart=/usr/bin/python3 {os.path.abspath(__file__)} worker
Restart=always
[Install]
WantedBy=default.target"""

def main():
    """CLI"""
    if len(sys.argv) < 2:
        print("Usage: add <name> <cmd> [priority] | worker [batch] | stats | bench | systemd")
        sys.exit(1)

    cmd = sys.argv[1]
    q = Q()

    if cmd == 'add':
        if len(sys.argv) < 4:
            print("Need name and command")
            sys.exit(1)
        id = q.add(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 0)
        print(f"Task {id}")

    elif cmd == 'worker':
        batch = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        print(f"Worker started (batch={batch})")
        worker(q, batch)

    elif cmd == 'stats':
        print(json.dumps(q.stats()))

    elif cmd == 'bench':
        bench()

    elif cmd == 'systemd':
        print(systemd())

    else:
        print(f"Unknown: {cmd}")

if __name__ == "__main__":
    main()