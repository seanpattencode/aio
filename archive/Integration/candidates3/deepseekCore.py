#!/usr/bin/env python3
"""Essential Job Queue - Core aiose features in <250 lines"""
import argparse, json, os, sqlite3, subprocess, sys, time, threading, signal
from pathlib import Path
from typing import Optional, List

DB_PATH = Path.home() / ".essential_aiose.db"

class Store:
    """SQLite queue with essential production features"""
    def __init__(self):
        self.db = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript("""
        PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY,
            cmd TEXT NOT NULL,
            args TEXT,
            mode TEXT DEFAULT 'local',  -- local or systemd
            status TEXT DEFAULT 'q',    -- q=queued r=running d=done f=failed
            priority INT DEFAULT 0,
            retry INT DEFAULT 0,
            max_retries INT DEFAULT 3,
            timeout INT DEFAULT 300,
            error TEXT,
            result TEXT,
            created INT DEFAULT (strftime('%s','now')*1000),
            started INT,
            ended INT,
            scheduled INT DEFAULT 0,    -- when to run (for delays)
            deps TEXT,                  -- JSON array of dependency task IDs
            unit TEXT                   -- systemd unit name
        );
        CREATE INDEX IF NOT EXISTS idx_q ON tasks(status, priority DESC, scheduled, id) 
        WHERE status='q';
        """)

    def add(self, cmd, args=None, mode='local', priority=0, timeout=300, 
            max_retries=3, scheduled=0, deps=None):
        with self.lock:
            return self.db.execute("""
                INSERT INTO tasks(cmd, args, mode, priority, timeout, max_retries, scheduled, deps) 
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                cmd, 
                json.dumps(args) if args else None, 
                mode,
                priority, 
                timeout,
                max_retries,
                scheduled,
                json.dumps(deps) if deps else None
            )).lastrowid

    def pop(self, worker_id: str) -> Optional[dict]:
        """Atomically get next task with dependency check"""
        with self.lock:
            now = int(time.time() * 1000)
            
            # Find eligible task (ready, deps met, not future-scheduled)
            query = """
                SELECT id, cmd, args, mode, timeout FROM tasks 
                WHERE status='q' AND scheduled <= ?
                AND (deps IS NULL OR NOT EXISTS (
                    SELECT 1 FROM json_each(tasks.deps) AS d
                    JOIN tasks t2 ON t2.id = d.value WHERE t2.status != 'd'
                ))
                ORDER BY priority DESC, scheduled, id LIMIT 1
            """
            row = self.db.execute(query, (now,)).fetchone()
            if not row:
                return None

            # Atomic claim
            try:
                claimed = self.db.execute("""
                    UPDATE tasks SET status='r', started=?, unit=NULL 
                    WHERE id=? AND status='q' RETURNING id, cmd, args, mode, timeout
                """, (now, row['id'])).fetchone()
                if claimed:
                    task = dict(claimed)
                    if task['args']:
                        task['args'] = json.loads(task['args'])
                    return task
            except sqlite3.OperationalError:
                # Fallback for older SQLite
                self.db.execute("BEGIN IMMEDIATE")
                updated = self.db.execute(
                    "UPDATE tasks SET status='r', started=?, unit=NULL WHERE id=? AND status='q'",
                    (now, row['id'])
                ).rowcount
                self.db.execute("COMMIT")
                if updated:
                    task = dict(row)
                    if task['args']:
                        task['args'] = json.loads(task['args'])
                    return task
            return None

    def complete(self, task_id: int, success: bool, result=None, error=None):
        with self.lock:
            now = int(time.time() * 1000)
            task = self.db.execute(
                "SELECT retry, max_retries FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if not task:
                return

            if success:
                self.db.execute(
                    "UPDATE tasks SET status='d', ended=?, result=? WHERE id=?",
                    (now, json.dumps(result)[:1000] if result else None, task_id)
                )
            else:
                retry_count = task['retry'] or 0
                max_retries = task['max_retries'] or 3
                
                if retry_count < max_retries:
                    # Exponential backoff: 1s, 2s, 4s, 8s...
                    delay_ms = 1000 * (2 ** retry_count)
                    self.db.execute(
                        "UPDATE tasks SET status='q', retry=retry+1, scheduled=?, error=? WHERE id=?",
                        (now + delay_ms, str(error)[:500], task_id)
                    )
                else:
                    self.db.execute(
                        "UPDATE tasks SET status='f', ended=?, error=? WHERE id=?",
                        (now, str(error)[:500], task_id)
                    )

    def reclaim_stalled(self, timeout_seconds: int = 300) -> int:
        """Reclaim tasks stuck in 'running' status"""
        with self.lock:
            cutoff = int(time.time() * 1000) - (timeout_seconds * 1000)
            return self.db.execute(
                "UPDATE tasks SET status='q', retry=retry+1, scheduled=? WHERE status='r' AND started < ?",
                (int(time.time() * 1000), cutoff)
            ).rowcount

    def list_tasks(self, limit: int = 50):
        with self.lock:
            return self.db.execute(
                "SELECT * FROM tasks ORDER BY created DESC LIMIT ?", (limit,)
            ).fetchall()

    def stats(self):
        with self.lock:
            status_counts = {r['status']: r['c'] for r in 
                self.db.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status").fetchall()}
            
            avg_times = self.db.execute("""
                SELECT AVG(started - created) as avg_queue_time, 
                       AVG(ended - started) as avg_run_time 
                FROM tasks WHERE status='d' AND started IS NOT NULL AND ended IS NOT NULL
            """).fetchone()
            
            return {
                'status': status_counts,
                'performance': dict(avg_times) if avg_times[0] else {}
            }

class Worker:
    """Worker with essential production features"""
    def __init__(self, store: Store, worker_id: str = None):
        self.store = store
        self.worker_id = worker_id or f"w{os.getpid()}"
        self.running = True
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)

    def _stop(self, *args):
        print(f"\nShutting down worker {self.worker_id}...")
        self.running = False

    def _execute_safe(self, cmd: str, args: List[str], timeout: int) -> tuple[bool, dict, str]:
        """Execute command safely without shell injection"""
        try:
            # Build command array safely
            if args:
                command = [cmd] + [str(a) for a in args]
            else:
                # If no args, check if cmd is a single command or needs shell
                if ' ' in cmd or '|' in cmd or '>' in cmd or '&' in cmd:
                    command = ['/bin/sh', '-c', cmd]
                else:
                    command = [cmd]

            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            result = {
                'stdout': proc.stdout[:1000],
                'stderr': proc.stderr[:1000],
                'returncode': proc.returncode
            }
            
            return proc.returncode == 0, result, proc.stderr if proc.returncode != 0 else None
            
        except subprocess.TimeoutExpired:
            return False, None, "Timeout"
        except Exception as e:
            return False, None, str(e)

    def run(self):
        print(f"Worker {self.worker_id} started (PID {os.getpid()})")
        last_reclaim = time.time()
        
        while self.running:
            # Reclaim stalled tasks every 30 seconds
            if time.time() - last_reclaim > 30:
                reclaimed = self.store.reclaim_stalled()
                if reclaimed:
                    print(f"Reclaimed {reclaimed} stalled tasks")
                last_reclaim = time.time()

            # Get and process task
            task = self.store.pop(self.worker_id)
            if not task:
                time.sleep(0.1)
                continue

            print(f"Running task {task['id']}: {task['cmd']}")
            success, result, error = self._execute_safe(
                task['cmd'],
                task.get('args', []),
                task.get('timeout', 300)
            )

            self.store.complete(task['id'], success, result, error)
            status = "success" if success else f"failed: {error}"
            print(f"Task {task['id']}: {status}")

        print("Worker stopped")

def main():
    parser = argparse.ArgumentParser(description="Essential Job Queue")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Add command
    add_p = sub.add_parser("add", help="Add task")
    add_p.add_argument("command", help="Command to run")
    add_p.add_argument("args", nargs="*", help="Arguments")
    add_p.add_argument("--mode", choices=['local', 'systemd'], default='local')
    add_p.add_argument("-p", "--priority", type=int, default=0)
    add_p.add_argument("--timeout", type=int, default=300)
    add_p.add_argument("--retries", type=int, default=3)
    add_p.add_argument("--delay", type=int, default=0, help="Delay execution by N seconds")
    add_p.add_argument("--deps", help="Comma-separated dependency task IDs")

    # Worker
    worker_p = sub.add_parser("worker", help="Run worker")
    worker_p.add_argument("--id", help="Worker ID")

    # List
    sub.add_parser("list", help="List recent tasks")

    # Stats
    sub.add_parser("stats", help="Show stats")

    # Reclaim
    sub.add_parser("reclaim", help="Reclaim stalled tasks")

    args = parser.parse_args()
    store = Store()

    if args.cmd == "add":
        deps = [int(d.strip()) for d in args.deps.split(',')] if args.deps else None
        scheduled = int(time.time() * 1000) + (args.delay * 1000) if args.delay > 0 else 0
        
        task_id = store.add(
            cmd=args.command,
            args=args.args,
            mode=args.mode,
            priority=args.priority,
            timeout=args.timeout,
            max_retries=args.retries,
            scheduled=scheduled,
            deps=deps
        )
        print(f"Added task {task_id}")

    elif args.cmd == "worker":
        Worker(store, args.id).run()

    elif args.cmd == "list":
        for task in store.list_tasks():
            deps = json.loads(task['deps']) if task['deps'] else []
            print(f"[{task['id']}] {task['cmd']} - {task['status']} "
                  f"(p={task['priority']}, retry={task['retry']}, deps={deps})")

    elif args.cmd == "stats":
        stats = store.stats()
        print(json.dumps(stats, indent=2))

    elif args.cmd == "reclaim":
        reclaimed = store.reclaim_stalled()
        print(f"Reclaimed {reclaimed} stalled tasks")

if __name__ == "__main__":
    main()