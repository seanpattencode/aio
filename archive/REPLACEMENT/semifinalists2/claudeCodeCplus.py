#!/usr/bin/env python3
"""claudeCodeC+: Minimal SQLite queue with safe pop, WAL, and sane defaults."""
import sqlite3, subprocess, json, time, sys, os, signal

NOW = lambda: int(time.time() * 1000)

class Q:
    """Essential queue backed by SQLite (WAL)."""
    def __init__(self, db="tasks.db"):
        self.c = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
        # Lean, portable PRAGMAs; WAL persists once set on file.
        for sql in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA temp_store=MEMORY",
            "PRAGMA busy_timeout=5000"
        ):
            self.c.execute(sql)
        # Schema: s ∈ {'q' queued, 'r' running, 'd' done, 'f' failed}
        self.c.execute("""
            CREATE TABLE IF NOT EXISTS t(
              id INTEGER PRIMARY KEY,
              cmd TEXT NOT NULL,
              p   INT  DEFAULT 0,
              s   TEXT DEFAULT 'q',
              at  INT  DEFAULT 0,
              w   TEXT,
              retries INT DEFAULT 0
            )""")
        self.c.execute(
            "CREATE INDEX IF NOT EXISTS i_q ON t(s,p DESC,at) WHERE s='q'")

    def add(self, cmd, p=0, at=None):
        """Add task (queued)."""
        return self.c.execute(
            "INSERT INTO t(cmd,p,at) VALUES(?,?,?)",
            (cmd, p, at if at is not None else NOW())
        ).lastrowid

    def _pop_with_returning(self):
        return self.c.execute("""
            UPDATE t SET s='r', w=?
            WHERE id=(SELECT id FROM t WHERE s='q' AND at<=? ORDER BY p DESC, at LIMIT 1)
            RETURNING id,cmd
        """, (str(os.getpid()), NOW())).fetchone()

    def pop(self):
        """Atomic pop; prefers RETURNING, falls back to locked SELECT+UPDATE."""
        try:
            row = self._pop_with_returning()
            return {'id': row[0], 'cmd': row[1]} if row else None
        except sqlite3.OperationalError:
            # Fallback for SQLite <3.35 (no RETURNING)
            self.c.execute("BEGIN IMMEDIATE")
            row = self.c.execute(
                "SELECT id,cmd FROM t WHERE s='q' AND at<=? ORDER BY p DESC, at LIMIT 1",
                (NOW(),)
            ).fetchone()
            if not row:
                self.c.execute("COMMIT")
                return None
            updated = self.c.execute(
                "UPDATE t SET s='r', w=? WHERE id=? AND s='q'",
                (str(os.getpid()), row[0])
            ).rowcount
            if updated == 1:
                self.c.execute("COMMIT")
                return {'id': row[0], 'cmd': row[1]}
            self.c.execute("ROLLBACK")
            return None

    def done(self, task_id, ok=True, worker=None):
        """Mark complete or retry; only the owner can finalize running tasks."""
        worker = worker or str(os.getpid())
        if ok:
            self.c.execute(
                "UPDATE t SET s='d', w=NULL WHERE id=? AND w=? AND s='r'",
                (task_id, worker))
            return
        # Failure path: attempt bounded retries with exponential backoff.
        row = self.c.execute(
            "SELECT retries FROM t WHERE id=? AND w=? AND s='r'",
            (task_id, worker)
        ).fetchone()
        if row is None:
            return
        r = row[0]
        if r < 3:
            delay = 1000 * (2 ** r)
            self.c.execute(
                "UPDATE t SET s='q', w=NULL, retries=retries+1, at=? WHERE id=?",
                (NOW() + delay, task_id)
            )
        else:
            self.c.execute(
                "UPDATE t SET s='f', w=NULL WHERE id=?",
                (task_id,))

    def stats(self):
        """Counts by state."""
        return {s: n for (s, n) in self.c.execute("SELECT s,COUNT(*) FROM t GROUP BY s")}

def worker(q=None, batch=1):
    """Simple worker loop."""
    q = q or Q()
    stop = {'v': False}
    def _halt(*_): stop.__setitem__('v', True)
    signal.signal(signal.SIGTERM, _halt)
    signal.signal(signal.SIGINT, _halt)
    wid = str(os.getpid())

    while not stop['v']:
        tasks = [q.pop() for _ in range(max(1, batch))]
        did = False
        for t in tasks:
            if not t: continue
            did = True
            try:
                # NOTE: for untrusted input, parse into argv and use shell=False.
                r = subprocess.run(t['cmd'], shell=True, capture_output=True, timeout=300)
                q.done(t['id'], r.returncode == 0, worker=wid)
            except Exception:
                q.done(t['id'], False, worker=wid)
        if not did:
            time.sleep(0.05)

def bench():
    """Tiny benchmark (inserts + pops)."""
    db = "bench.db"
    if os.path.exists(db):
        os.unlink(db)
    q = Q(db)
    start = time.perf_counter()
    for i in range(1000):
        q.add(f"echo {i}", i % 10)
    t1 = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    for _ in range(100):
        q.pop()
    t2 = (time.perf_counter() - start) * 1000

    print(f"claudeCodeC+ bench:\n"
          f"1000 inserts: {t1:.2f}ms ({t1/1000:.4f}ms/op)\n"
          f"100 pops:    {t2:.2f}ms ({t2/100:.4f}ms/op)")

def systemd():
    """Emit a minimal user service unit."""
    return f"""[Unit]
Description=Task Worker (SQLite)
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 {os.path.abspath(__file__)} worker
Restart=always
RestartSec=2
KillMode=mixed
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=default.target
"""

def main():
    if len(sys.argv) < 2:
        print("Usage: add <cmd> [priority] | worker [batch] | stats | bench | systemd")
        sys.exit(1)

    cmd = sys.argv[1]
    q = Q()

    if cmd == 'add':
        if len(sys.argv) < 3:
            print("Need command"); sys.exit(1)
        pr = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        tid = q.add(sys.argv[2], pr)
        print(f"Task {tid}")

    elif cmd == 'worker':
        batch = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        print(f"Worker started (batch={batch}) pid={os.getpid()}")
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