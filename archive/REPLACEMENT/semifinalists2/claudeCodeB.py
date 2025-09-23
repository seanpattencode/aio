#!/usr/bin/env python3
"""
claudeCodeB: Ultimate SQLite Task Queue - Faster, Smaller, Better
Combines only the winning patterns, eliminates all overhead
"""
import sqlite3, subprocess, json, time, sys, os, signal
from pathlib import Path
from typing import Optional, Dict, Any, List

DB = Path(__file__).parent / "tasks_b.db"

class UltraQueue:
    """Minimal, blazing-fast queue with all essential features"""

    def __init__(self, db=DB):
        # Single persistent connection - fastest pattern from claude1
        self.c = sqlite3.connect(str(db), isolation_level=None, check_same_thread=False)
        self.c.row_factory = sqlite3.Row

        # Optimal pragmas - proven fastest combination
        self.c.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA temp_store=MEMORY;
            PRAGMA mmap_size=268435456;
            PRAGMA cache_size=-64000;
            PRAGMA busy_timeout=5000;

            CREATE TABLE IF NOT EXISTS t (
                id INTEGER PRIMARY KEY,
                cmd TEXT,
                p INTEGER DEFAULT 0,
                s TEXT DEFAULT 'q',
                at INTEGER DEFAULT 0,
                lu INTEGER,
                w TEXT,
                r INTEGER DEFAULT 0,
                d TEXT,
                uk TEXT UNIQUE,
                pid TEXT
            );
            CREATE INDEX IF NOT EXISTS ix ON t(s,p DESC,at) WHERE s='q';
            CREATE INDEX IF NOT EXISTS il ON t(lu) WHERE s='l';

            CREATE TABLE IF NOT EXISTS td (
                c INTEGER, p INTEGER,
                PRIMARY KEY(c,p),
                FOREIGN KEY(c) REFERENCES t(id),
                FOREIGN KEY(p) REFERENCES t(id)
            );
        """)

    def add(self, cmd: str, p=0, at=0, uk=None, pid=None, d=None) -> Optional[int]:
        """Add task - ultra-optimized"""
        try:
            at = at or int(time.time()*1000)
            r = self.c.execute(
                "INSERT INTO t(cmd,p,at,uk,pid,d) VALUES(?,?,?,?,?,?)",
                (cmd, p, at, uk, json.dumps(pid) if pid else None, d)
            ).lastrowid
            if pid and r:
                for parent in (pid if isinstance(pid, list) else [pid]):
                    self.c.execute("INSERT INTO td VALUES(?,?)", (r, parent))
            return r
        except sqlite3.IntegrityError:
            return None

    def pop(self, w=None) -> Optional[Dict]:
        """Atomic pop - fastest possible"""
        w = w or f"w{os.getpid()}"
        now = int(time.time()*1000)

        # Single atomic UPDATE with RETURNING - no separate SELECT
        r = self.c.execute("""
            UPDATE t SET s='r', w=?, lu=?
            WHERE id=(
                SELECT id FROM t WHERE s='q' AND at<=?
                AND NOT EXISTS(
                    SELECT 1 FROM td JOIN t p ON p.id=td.p
                    WHERE td.c=t.id AND p.s!='d'
                )
                ORDER BY p DESC, at LIMIT 1
            ) RETURNING id, cmd, d
        """, (w, now+300000, now)).fetchone()

        return {'id': r['id'], 'cmd': r['cmd'], 'd': json.loads(r['d']) if r['d'] else None} if r else None

    def done(self, id: int, ok=True, e=None):
        """Complete task - minimal ops"""
        if ok:
            self.c.execute("UPDATE t SET s='d',lu=NULL,w=NULL WHERE id=?", (id,))
        else:
            r = self.c.execute("SELECT r FROM t WHERE id=?", (id,)).fetchone()
            if r and r['r'] < 3:
                # Simple exponential backoff
                self.c.execute(
                    "UPDATE t SET s='q',r=r+1,at=?,lu=NULL,w=NULL WHERE id=?",
                    (int(time.time()*1000) + (1000 * 2**r['r']), id)
                )
            else:
                self.c.execute("UPDATE t SET s='f',lu=NULL,w=NULL WHERE id=?", (id,))

    def claim(self, w=None, n=1) -> List[Dict]:
        """Batch claim with lease"""
        w = w or f"w{os.getpid()}"
        now = int(time.time()*1000)
        lu = now + 300000

        # Claim eligible tasks
        ids = [r[0] for r in self.c.execute("""
            SELECT id FROM t WHERE s='q' AND at<=?
            AND NOT EXISTS(
                SELECT 1 FROM td JOIN t p ON p.id=td.p
                WHERE td.c=t.id AND p.s!='d'
            )
            ORDER BY p DESC, at LIMIT ?
        """, (now, n)).fetchall()]

        if ids:
            self.c.execute(
                f"UPDATE t SET s='l',w=?,lu=? WHERE id IN ({','.join('?'*len(ids))})",
                [w, lu] + ids
            )
            return [{'id': r['id'], 'cmd': r['cmd'], 'd': json.loads(r['d']) if r['d'] else None}
                    for r in self.c.execute(f"SELECT id,cmd,d FROM t WHERE id IN ({','.join('?'*len(ids))})", ids)]
        return []

    def reclaim(self):
        """Reclaim expired leases"""
        self.c.execute("UPDATE t SET s='q',lu=NULL,w=NULL WHERE s='l' AND lu<?", (int(time.time()*1000),))

    def stats(self) -> Dict:
        """Quick stats"""
        return {r['s']: r['c'] for r in self.c.execute("SELECT s,COUNT(*) c FROM t GROUP BY s")}

class Worker:
    """Ultra-fast worker"""

    def __init__(self, q: UltraQueue, w=None):
        self.q = q
        self.w = w or f"w{os.getpid()}"
        self.run = True
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, 'run', False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, 'run', False))

    def work(self, batch=1):
        """Main loop - optimized"""
        while self.run:
            # Reclaim periodically
            if int(time.time()) % 10 == 0:
                self.q.reclaim()

            # Process batch
            tasks = self.q.claim(self.w, batch) if batch > 1 else [self.q.pop(self.w)]

            for t in tasks:
                if t and self.run:
                    try:
                        r = subprocess.run(t['cmd'], shell=True, capture_output=True, timeout=290)
                        self.q.done(t['id'], r.returncode == 0)
                    except:
                        self.q.done(t['id'], False)

            if not any(tasks):
                time.sleep(0.05)

def systemd_unit(mode='single'):
    """Generate systemd unit"""
    p = Path(__file__).absolute()
    return f"""[Unit]
Description=Task Worker
After=network.target

[Service]
ExecStart=/usr/bin/python3 {p} worker {'--batch 5' if mode=='batch' else ''}
Restart=always
RestartSec=3

[Install]
WantedBy=default.target"""

def main():
    """CLI - minimal but complete"""
    q = UltraQueue()

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <add|work|worker|stats|test|bench|install>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'add':
        # Add task: add <cmd> [priority] [delay_ms] [unique_key] [parent_ids]
        if len(sys.argv) < 3:
            print("Usage: add <command> [priority] [delay_ms] [unique_key] [parent_ids]")
            sys.exit(1)

        c = sys.argv[2]
        p = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        at = int(time.time()*1000) + int(sys.argv[4]) if len(sys.argv) > 4 else 0
        uk = sys.argv[5] if len(sys.argv) > 5 else None
        pid = json.loads(sys.argv[6]) if len(sys.argv) > 6 else None

        id = q.add(c, p, at, uk, pid)
        print(f"Task {id}" if id else "Duplicate")

    elif cmd in ('work', 'worker'):
        # Run worker
        batch = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else 1
        print(f"Worker started (batch={batch})")
        Worker(q).work(batch)

    elif cmd == 'stats':
        # Show stats
        s = q.stats()
        print(json.dumps(s, indent=2))

    elif cmd == 'test':
        # Test workflow
        p1 = q.add("echo 'Parent task'", 10)
        print(f"Parent: {p1}")

        for i in range(3):
            c = q.add(f"echo 'Child {i}'", 5, pid=[p1])
            print(f"Child {i}: {c}")

        d = q.add("echo 'Delayed'", 1, at=int(time.time()*1000)+5000, uk="delayed_task")
        print(f"Delayed: {d}")

        print("\nRun 'worker' to process")

    elif cmd == 'bench':
        # Benchmark
        print("Benchmarking...")

        # Fast inserts
        s = time.perf_counter()
        for i in range(1000):
            q.add(f"echo {i}", i%10)
        t1 = (time.perf_counter()-s)*1000

        # With dependencies
        s = time.perf_counter()
        p = q.add("echo parent", 10)
        for i in range(999):
            q.add(f"echo c{i}", 5, pid=[p] if i<100 else None)
        t2 = (time.perf_counter()-s)*1000

        # Pops
        s = time.perf_counter()
        for _ in range(100):
            q.pop()
        t3 = (time.perf_counter()-s)*1000

        print(f"""
=== claudeCodeB Performance ===
1000 simple inserts: {t1:.2f}ms ({t1/1000:.4f}ms per op)
1000 w/deps inserts: {t2:.2f}ms ({t2/1000:.4f}ms per op)
100 atomic pops:     {t3:.2f}ms ({t3/100:.4f}ms per op)
        """)

    elif cmd == 'install':
        # Install systemd unit
        u = Path.home() / '.config/systemd/user/task-worker.service'
        u.parent.mkdir(parents=True, exist_ok=True)
        u.write_text(systemd_unit('batch' if '--batch' in sys.argv else 'single'))
        subprocess.run(['systemctl', '--user', 'daemon-reload'])
        print(f"Installed: {u}\nStart with: systemctl --user start task-worker")

    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()