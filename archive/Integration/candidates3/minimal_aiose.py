#!/usr/bin/env python3
"""Minimal Job Queue - Essential aiose in <200 lines"""
import argparse, json, os, sqlite3, subprocess, sys, time, threading, signal
from pathlib import Path

DB_PATH = Path.home() / ".minimal_aiose.db"

class Store:
    """Minimal SQLite queue with essential operations"""
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
            status TEXT DEFAULT 'q',  -- q=queued r=running d=done f=failed
            priority INT DEFAULT 0,
            retry INT DEFAULT 0,
            error TEXT,
            result TEXT,
            created INT DEFAULT (strftime('%s','now')*1000),
            started INT,
            ended INT
        );
        CREATE INDEX IF NOT EXISTS idx_q ON tasks(status, priority DESC, id) WHERE status='q';
        """)

    def add(self, cmd, args=None, priority=0):
        with self.lock:
            return self.db.execute(
                "INSERT INTO tasks(cmd, args, priority) VALUES (?,?,?)",
                (cmd, json.dumps(args) if args else None, priority)
            ).lastrowid

    def pop(self):
        """Atomically get next task"""
        with self.lock:
            now = int(time.time()*1000)
            # Try atomic RETURNING first
            try:
                row = self.db.execute("""
                    UPDATE tasks SET status='r', started=?
                    WHERE id=(SELECT id FROM tasks WHERE status='q' ORDER BY priority DESC, id LIMIT 1)
                    RETURNING id, cmd, args
                """, (now,)).fetchone()
                return dict(row) if row else None
            except:
                # Fallback for older SQLite
                row = self.db.execute(
                    "SELECT id, cmd, args FROM tasks WHERE status='q' ORDER BY priority DESC, id LIMIT 1"
                ).fetchone()
                if row:
                    n = self.db.execute(
                        "UPDATE tasks SET status='r', started=? WHERE id=? AND status='q'",
                        (now, row['id'])
                    ).rowcount
                    return dict(row) if n else None
        return None

    def complete(self, task_id, success, result=None, error=None):
        with self.lock:
            now = int(time.time()*1000)
            task = self.db.execute("SELECT retry FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task: return

            if success:
                self.db.execute(
                    "UPDATE tasks SET status='d', ended=?, result=? WHERE id=?",
                    (now, json.dumps(result)[:500] if result else None, task_id)
                )
            elif task['retry'] < 3:
                # Retry with exponential backoff
                self.db.execute(
                    "UPDATE tasks SET status='q', retry=retry+1, error=? WHERE id=?",
                    (str(error)[:500], task_id)
                )
            else:
                self.db.execute(
                    "UPDATE tasks SET status='f', ended=?, error=? WHERE id=?",
                    (now, str(error)[:500], task_id)
                )

    def list_tasks(self):
        with self.lock:
            return self.db.execute("SELECT * FROM tasks ORDER BY created DESC LIMIT 50").fetchall()

    def stats(self):
        with self.lock:
            rows = self.db.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status").fetchall()
            return {r['status']: r['c'] for r in rows}

class Worker:
    """Minimal worker that processes tasks"""
    def __init__(self, store):
        self.store = store
        self.running = True
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, 'running', False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, 'running', False))

    def run(self):
        print(f"Worker started (PID {os.getpid()})")
        while self.running:
            task = self.store.pop()
            if not task:
                time.sleep(0.1)
                continue

            print(f"Running task {task['id']}: {task['cmd']}")
            try:
                # Build command
                cmd = task['cmd']
                if task['args']:
                    args = json.loads(task['args'])
                    import shlex
                    cmd = f"{cmd} {' '.join(shlex.quote(str(a)) for a in args)}"

                # Execute
                proc = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=60
                )

                # Complete
                self.store.complete(
                    task['id'],
                    proc.returncode == 0,
                    {'stdout': proc.stdout[:500], 'stderr': proc.stderr[:500]},
                    proc.stderr if proc.returncode != 0 else None
                )
                print(f"Task {task['id']}: {'success' if proc.returncode == 0 else 'failed'}")

            except subprocess.TimeoutExpired:
                self.store.complete(task['id'], False, error="Timeout")
                print(f"Task {task['id']}: timeout")
            except Exception as e:
                self.store.complete(task['id'], False, error=str(e))
                print(f"Task {task['id']}: error - {e}")

        print("Worker stopped")

def main():
    parser = argparse.ArgumentParser(description="Minimal Job Queue")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Add command
    add_p = sub.add_parser("add", help="Add task")
    add_p.add_argument("command", help="Command to run")
    add_p.add_argument("-p", "--priority", type=int, default=0, help="Priority")
    add_p.add_argument("args", nargs="*", help="Arguments")

    # Worker
    sub.add_parser("worker", help="Run worker")

    # List
    sub.add_parser("list", help="List tasks")

    # Stats
    sub.add_parser("stats", help="Show stats")

    args = parser.parse_args()
    store = Store()

    if args.cmd == "add":
        task_id = store.add(args.command, args.args if args.args else None, args.priority)
        print(f"Added task {task_id}")

    elif args.cmd == "worker":
        Worker(store).run()

    elif args.cmd == "list":
        for task in store.list_tasks():
            print(f"[{task['id']}] {task['cmd']} - {task['status']} (p={task['priority']})")

    elif args.cmd == "stats":
        stats = store.stats()
        print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()