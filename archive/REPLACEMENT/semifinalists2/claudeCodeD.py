#!/usr/bin/env python3
"""
claudeCodeD: Ultimate Performance + Production Features
Combines claudeCodeC minimalism with production patterns from Chrome/Firefox/Android
"""
import sqlite3, subprocess, json, time, sys, os, signal, threading
from typing import Optional, Dict, Any

# Optimized pragmas from production systems
PRAGMAS = [
    "PRAGMA journal_mode=WAL",        # Universal best practice
    "PRAGMA synchronous=NORMAL",      # Safe with WAL
    "PRAGMA cache_size=-8000",        # 8MB cache (Chrome)
    "PRAGMA temp_store=MEMORY",       # Fast temp ops
    "PRAGMA mmap_size=268435456",     # 256MB mmap
    "PRAGMA busy_timeout=5000",       # 5s timeout
    "PRAGMA wal_autocheckpoint=1000", # Firefox pattern
]

class TaskQueue:
    """Ultra-fast queue with production robustness"""

    def __init__(self, db="tasks_d.db"):
        # Single persistent connection for speed (claudeCodeC pattern)
        self.c = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.lock = threading.RLock()  # Thread safety

        # Apply optimized pragmas
        for pragma in PRAGMAS:
            self.c.execute(pragma)

        # Hybrid schema: minimal but complete
        self.c.execute("""
            CREATE TABLE IF NOT EXISTS t (
                id INTEGER PRIMARY KEY,
                cmd TEXT NOT NULL,
                p INT DEFAULT 0,      -- priority
                s TEXT DEFAULT 'q',   -- status: q=queued r=running d=done f=failed
                at INT DEFAULT 0,     -- scheduled_at (ms)
                w TEXT,               -- worker_id
                r INT DEFAULT 0,      -- retry_count
                e TEXT,               -- error_message
                res TEXT,             -- result
                ct INT DEFAULT (strftime('%s','now')*1000),  -- created_at
                st INT,               -- started_at
                et INT,               -- ended_at
                -- Dependencies (simplified)
                dep TEXT              -- JSON array of dependency IDs
            )
        """)

        # Optimized composite index (production pattern)
        self.c.execute("""
            CREATE INDEX IF NOT EXISTS ix ON t(s,p DESC,at,id)
            WHERE s IN ('q','r')
        """)

        # Metrics table (Chrome pattern, simplified)
        self.c.execute("""
            CREATE TABLE IF NOT EXISTS m (
                task_id INTEGER PRIMARY KEY,
                qt REAL,  -- queue_time
                et REAL,  -- exec_time
                FOREIGN KEY (task_id) REFERENCES t(id) ON DELETE CASCADE
            )
        """)

    def add(self, cmd: str, p: int = 0, at: Optional[int] = None,
            dep: Optional[list] = None) -> int:
        """Add task with optional dependencies"""
        at = at or int(time.time() * 1000)
        dep_json = json.dumps(dep) if dep else None

        with self.lock:
            return self.c.execute(
                "INSERT INTO t(cmd,p,at,dep) VALUES(?,?,?,?)",
                (cmd, p, at, dep_json)
            ).lastrowid

    def pop(self, worker_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Atomic pop with dependency checking"""
        worker_id = worker_id or str(os.getpid())
        now = int(time.time() * 1000)

        with self.lock:
            # Find next eligible task (with dependency check)
            row = self.c.execute("""
                SELECT id, cmd FROM t
                WHERE s='q' AND at<=?
                AND (dep IS NULL OR NOT EXISTS (
                    SELECT 1 FROM json_each(t.dep) AS d
                    JOIN t AS dt ON dt.id = d.value
                    WHERE dt.s != 'd'
                ))
                ORDER BY p DESC, at, id
                LIMIT 1
            """, (now,)).fetchone()

            if not row:
                return None

            # Atomic claim using RETURNING (fastest pattern)
            try:
                result = self.c.execute("""
                    UPDATE t SET s='r', w=?, st=?
                    WHERE id=? AND s='q'
                    RETURNING id, cmd
                """, (worker_id, now, row['id'])).fetchone()

                return {'id': result['id'], 'cmd': result['cmd']} if result else None
            except sqlite3.OperationalError:
                # Fallback for older SQLite
                self.c.execute("BEGIN IMMEDIATE")
                updated = self.c.execute(
                    "UPDATE t SET s='r', w=?, st=? WHERE id=? AND s='q'",
                    (worker_id, now, row['id'])
                ).rowcount
                self.c.execute("COMMIT")

                return {'id': row['id'], 'cmd': row['cmd']} if updated else None

    def done(self, task_id: int, ok: bool = True, result: Any = None,
             error: str = None, worker_id: Optional[str] = None):
        """Complete or retry with exponential backoff"""
        worker_id = worker_id or str(os.getpid())
        now = int(time.time() * 1000)

        with self.lock:
            if ok:
                # Success: mark done and record metrics
                row = self.c.execute(
                    "SELECT ct, st FROM t WHERE id=? AND w=?",
                    (task_id, worker_id)
                ).fetchone()

                if row:
                    # Update task
                    self.c.execute("""
                        UPDATE t SET s='d', et=?, res=?, w=NULL
                        WHERE id=? AND w=?
                    """, (now, json.dumps(result) if result else None,
                         task_id, worker_id))

                    # Record metrics (Chrome pattern)
                    if row['st']:
                        qt = (row['st'] - row['ct']) / 1000.0
                        et = (now - row['st']) / 1000.0
                        self.c.execute(
                            "INSERT OR REPLACE INTO m(task_id,qt,et) VALUES(?,?,?)",
                            (task_id, qt, et)
                        )
            else:
                # Failure: retry with exponential backoff
                row = self.c.execute(
                    "SELECT r FROM t WHERE id=? AND w=?",
                    (task_id, worker_id)
                ).fetchone()

                if row and row['r'] < 3:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = 1000 * (2 ** row['r'])
                    self.c.execute("""
                        UPDATE t SET s='q', at=?, r=r+1, e=?, w=NULL
                        WHERE id=? AND w=?
                    """, (now + delay, error, task_id, worker_id))
                else:
                    # Final failure
                    self.c.execute("""
                        UPDATE t SET s='f', et=?, e=?, w=NULL
                        WHERE id=? AND w=?
                    """, (now, error, task_id, worker_id))

    def reclaim_stalled(self, timeout_ms: int = 300000):
        """Reclaim stalled tasks (production pattern)"""
        cutoff = int(time.time() * 1000) - timeout_ms
        with self.lock:
            return self.c.execute("""
                UPDATE t SET s='q', w=NULL, r=r+1
                WHERE s='r' AND st < ?
            """, (cutoff,)).rowcount

    def stats(self) -> Dict[str, Any]:
        """Comprehensive stats"""
        with self.lock:
            # Task counts
            counts = {row['s']: row['c'] for row in self.c.execute(
                "SELECT s, COUNT(*) c FROM t GROUP BY s"
            )}

            # Performance metrics
            perf = self.c.execute("""
                SELECT AVG(qt) avg_qt, AVG(et) avg_et,
                       MAX(qt) max_qt, MAX(et) max_et
                FROM m
            """).fetchone()

            # WAL status
            wal = self.c.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()

            return {
                'tasks': counts,
                'perf': dict(perf) if perf else {},
                'wal_pages': wal[1] if wal else 0
            }

    def cleanup(self, days: int = 7):
        """Clean old completed tasks"""
        cutoff = int(time.time() * 1000) - (days * 86400000)
        with self.lock:
            deleted = self.c.execute(
                "DELETE FROM t WHERE s IN ('d','f') AND et < ?",
                (cutoff,)
            ).rowcount

            # Vacuum if fragmented (Firefox pattern)
            page_count = self.c.execute("PRAGMA page_count").fetchone()[0]
            freelist = self.c.execute("PRAGMA freelist_count").fetchone()[0]

            if freelist > page_count * 0.3:
                self.c.execute("VACUUM")

            return deleted

class Worker:
    """High-performance worker with graceful shutdown"""

    def __init__(self, queue: TaskQueue, worker_id: Optional[str] = None):
        self.q = queue
        self.w = worker_id or f"w{os.getpid()}"
        self.running = True
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, *_):
        self.running = False

    def run(self, batch: int = 1):
        """Main worker loop"""
        print(f"Worker {self.w} started (batch={batch})")
        reclaim_counter = 0

        while self.running:
            # Periodic maintenance
            reclaim_counter += 1
            if reclaim_counter % 100 == 0:
                reclaimed = self.q.reclaim_stalled()
                if reclaimed:
                    print(f"Reclaimed {reclaimed} stalled tasks")

            # Process batch
            tasks = []
            for _ in range(batch):
                task = self.q.pop(self.w)
                if task:
                    tasks.append(task)

            if not tasks:
                time.sleep(0.05)
                continue

            for task in tasks:
                if not self.running:
                    break

                try:
                    # Execute command
                    result = subprocess.run(
                        task['cmd'],
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=290
                    )

                    self.q.done(
                        task['id'],
                        result.returncode == 0,
                        {'stdout': result.stdout[:1000], 'stderr': result.stderr[:1000]},
                        result.stderr if result.returncode != 0 else None,
                        self.w
                    )

                except subprocess.TimeoutExpired:
                    self.q.done(task['id'], False, error="TIMEOUT", worker_id=self.w)
                except Exception as e:
                    self.q.done(task['id'], False, error=str(e), worker_id=self.w)

def bench():
    """Comprehensive benchmark"""
    import os
    db = "bench_d.db"
    if os.path.exists(db):
        os.unlink(db)

    q = TaskQueue(db)

    # Test 1: Simple inserts
    start = time.perf_counter()
    for i in range(1000):
        q.add(f"echo {i}", i % 10)
    t1 = (time.perf_counter() - start) * 1000

    # Test 2: With dependencies
    start = time.perf_counter()
    parent = q.add("echo parent", 10)
    for i in range(100):
        q.add(f"echo child{i}", 5, dep=[parent])
    t2 = (time.perf_counter() - start) * 1000

    # Test 3: Pops
    start = time.perf_counter()
    for _ in range(100):
        q.pop()
    t3 = (time.perf_counter() - start) * 1000

    # Test 4: Complete tasks
    start = time.perf_counter()
    for i in range(1, 51):
        q.done(i, True, {'test': 'result'})
    t4 = (time.perf_counter() - start) * 1000

    stats = q.stats()

    print(f"""
=== claudeCodeD Performance ===
1000 inserts:      {t1:.2f}ms ({t1/1000:.4f}ms/op)
101 w/deps:        {t2:.2f}ms ({t2/101:.4f}ms/op)
100 pops:          {t3:.2f}ms ({t3/100:.4f}ms/op)
50 completions:    {t4:.2f}ms ({t4/50:.4f}ms/op)

Stats: {json.dumps(stats, indent=2)}
""")

def systemd():
    """Generate production systemd unit"""
    return f"""[Unit]
Description=claudeCodeD Task Worker
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {os.path.abspath(__file__)} worker
Restart=always
RestartSec=3
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=10

# Production settings
LimitNOFILE=65536
Nice=-5
PrivateTmp=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target"""

def main():
    """Enhanced CLI"""
    if len(sys.argv) < 2:
        print("""Usage:
  add <cmd> [priority] [delay_ms] [deps]  - Add task
  worker [batch]                          - Run worker
  stats                                   - Show statistics
  bench                                   - Run benchmark
  cleanup [days]                          - Clean old tasks
  systemd                                 - Generate systemd unit""")
        sys.exit(1)

    cmd = sys.argv[1]
    q = TaskQueue()

    if cmd == 'add':
        if len(sys.argv) < 3:
            print("Need command")
            sys.exit(1)

        command = sys.argv[2]
        priority = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        delay = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        deps = json.loads(sys.argv[5]) if len(sys.argv) > 5 else None

        at = int(time.time() * 1000) + delay if delay else None
        task_id = q.add(command, priority, at, deps)
        print(f"Task {task_id}")

    elif cmd == 'worker':
        batch = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        worker = Worker(q)
        worker.run(batch)

    elif cmd == 'stats':
        stats = q.stats()
        print(json.dumps(stats, indent=2))

    elif cmd == 'bench':
        bench()

    elif cmd == 'cleanup':
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        deleted = q.cleanup(days)
        print(f"Deleted {deleted} old tasks")

    elif cmd == 'systemd':
        print(systemd())

    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()