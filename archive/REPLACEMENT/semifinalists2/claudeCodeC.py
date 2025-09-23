#!/usr/bin/env python3
"""claudeCodeC: Perfect Minimalism - Does Less, Better"""
import sqlite3, subprocess, json, time, sys, os, signal

class Q:
    """The Essential Queue - Nothing More"""
    def __init__(self, db="tasks.db"):
        self.c = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
        for sql in [
            "PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL", "PRAGMA temp_store=MEMORY",
            "PRAGMA mmap_size=268435456", "PRAGMA cache_size=-64000",
            """CREATE TABLE IF NOT EXISTS t (
                id INTEGER PRIMARY KEY, cmd TEXT, p INT DEFAULT 0,
                s TEXT DEFAULT 'q', at INT DEFAULT 0, w TEXT, r INT DEFAULT 0
            )""",
            "CREATE INDEX IF NOT EXISTS i ON t(s,p DESC,at) WHERE s='q'"
        ]: self.c.execute(sql)

    def add(self, cmd, p=0, at=None):
        """Add task"""
        return self.c.execute("INSERT INTO t(cmd,p,at) VALUES(?,?,?)",
            (cmd, p, at or int(time.time()*1000))).lastrowid

    def pop(self):
        """Get next task atomically"""
        r = self.c.execute("""
            UPDATE t SET s='r', w=? WHERE id=(
                SELECT id FROM t WHERE s='q' AND at<=?
                ORDER BY p DESC, at LIMIT 1
            ) RETURNING id, cmd
        """, (os.getpid(), int(time.time()*1000))).fetchone()
        return {'id': r[0], 'cmd': r[1]} if r else None

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

    def stats(self):
        """Get counts"""
        return {r[0]: r[1] for r in self.c.execute("SELECT s,COUNT(*) FROM t GROUP BY s")}

def worker(q=None, batch=1):
    """Process tasks"""
    q = q or Q()
    run = True
    signal.signal(signal.SIGTERM, lambda *_: globals().update(run=False))
    signal.signal(signal.SIGINT, lambda *_: globals().update(run=False))

    while run:
        tasks = [q.pop() for _ in range(batch)]
        for t in tasks:
            if t:
                try:
                    r = subprocess.run(t['cmd'], shell=True, capture_output=True, timeout=300)
                    q.done(t['id'], r.returncode == 0)
                except:
                    q.done(t['id'], False)
        if not any(tasks):
            time.sleep(0.05)

def bench():
    """Benchmark"""
    q = Q("bench.db")
    os.unlink("bench.db") if os.path.exists("bench.db") else None

    # Insert test
    s = time.perf_counter()
    for i in range(1000):
        q.add(f"echo {i}", i%10)
    t1 = (time.perf_counter()-s)*1000

    # Pop test
    s = time.perf_counter()
    for _ in range(100):
        q.pop()
    t2 = (time.perf_counter()-s)*1000

    print(f"""claudeCodeC Benchmark:
1000 inserts: {t1:.2f}ms ({t1/1000:.4f}ms per op)
100 pops: {t2:.2f}ms ({t2/100:.4f}ms per op)""")

def systemd():
    """Generate systemd unit"""
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
        print("Usage: add <cmd> [priority] | worker [batch] | stats | bench | systemd")
        sys.exit(1)

    cmd = sys.argv[1]
    q = Q()

    if cmd == 'add':
        if len(sys.argv) < 3:
            print("Need command")
            sys.exit(1)
        id = q.add(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
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