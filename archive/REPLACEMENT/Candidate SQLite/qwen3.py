#!/usr/bin/env python3

"""

AIOS SQLite Task Queue — Ultra-minimal, ultra-fast, systemd-compatible

Designed for <800 lines. Inspired by Android WorkManager, iOS NSOperationQueue, and Linux cron.

Uses SQLite WAL, advisory locks, and exponential backoff.

Integrates with SystemdOrchestrator via job names.

"""

import sqlite3
import json
import time
import threading
import os
import random
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Dict, Any, List, Tuple

# --- CONFIG ---
DB_PATH = Path("~/.aios/tasks.db").expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
MAX_RETRIES = 5
POLL_INTERVAL = 1.0  # seconds
LOCK_TIMEOUT = 30.0

# --- SCHEMA ---
SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-10000;  -- 10MB cache
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    command TEXT NOT NULL,
    payload TEXT,  -- JSON args
    status TEXT NOT NULL DEFAULT 'pending', -- pending|running|completed|failed|canceled
    retries INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 5,
    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    started_at REAL,
    completed_at REAL,
    error TEXT,
    output TEXT,
    next_retry_at REAL,
    pid INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_status_next_retry ON tasks(status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_job_name ON tasks(job_name);
"""

# --- LOCKING ---
def acquire_lock(conn: sqlite3.Connection, lock_name: str, timeout: float = LOCK_TIMEOUT) -> bool:
    """Advisory lock using SQLite's application_id as namespace"""
    lock_key = hash(lock_name) % (2**31 - 1)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            cursor = conn.execute("SELECT pg_try_advisory_lock(?)", (lock_key,))
            if cursor.fetchone()[0]:
                return True
        except sqlite3.OperationalError:
            pass
        time.sleep(0.1)
    return False

def release_lock(conn: sqlite3.Connection, lock_name: str):
    lock_key = hash(lock_name) % (2**31 - 1)
    conn.execute("SELECT pg_advisory_unlock(?)", (lock_key,))

# --- CONTEXT MANAGER ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=LOCK_TIMEOUT, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
    finally:
        conn.close()

# --- TASK QUEUE ---
class AIOSTaskQueue:
    def __init__(self):
        self._local = threading.local()
        self._ensure_schema()

    def _ensure_schema(self):
        with get_db_connection() as conn:
            conn.executescript(SCHEMA)

    def add_task(self, job_name: str, command: str, payload: Optional[Dict] = None, max_retries: int = MAX_RETRIES) -> int:
        """Add a task to queue"""
        with get_db_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO tasks (job_name, command, payload, max_retries, status, next_retry_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
            """, (job_name, command, json.dumps(payload) if payload else None, max_retries, time.time()))
            conn.commit()
            return cursor.lastrowid

    def get_next_task(self) -> Optional[Dict[str, Any]]:
        """Atomic fetch of next pending/failed-retryable task"""
        with get_db_connection() as conn:
            if not acquire_lock(conn, "task_fetch"):
                return None
            try:
                now = time.time()
                cursor = conn.execute("""
                    SELECT * FROM tasks
                    WHERE status IN ('pending', 'failed')
                    AND (next_retry_at IS NULL OR next_retry_at <= ?)
                    ORDER BY created_at ASC
                    LIMIT 1
                """, (now,))
                row = cursor.fetchone()
                if not row:
                    return None

                # Mark as running
                conn.execute("""
                    UPDATE tasks
                    SET status = 'running', started_at = ?, pid = ?
                    WHERE id = ?
                """, (now, os.getpid(), row['id']))
                conn.commit()

                task = dict(row)
                if task['payload']:
                    task['payload'] = json.loads(task['payload'])
                return task
            finally:
                release_lock(conn, "task_fetch")

    def complete_task(self, task_id: int, output: str = "", error: str = ""):
        """Mark task as completed or failed"""
        with get_db_connection() as conn:
            if error:
                retries = conn.execute("SELECT retries FROM tasks WHERE id = ?", (task_id,)).fetchone()[0]
                if retries >= conn.execute("SELECT max_retries FROM tasks WHERE id = ?", (task_id,)).fetchone()[0]:
                    status = 'failed'
                    next_retry_at = None
                else:
                    # Exponential backoff: 2^retries seconds, capped at 5 min
                    delay = min(2 ** retries, 300)
                    next_retry_at = time.time() + delay + random.uniform(0, 1)
                    status = 'failed'
                    conn.execute("""
                        UPDATE tasks
                        SET retries = retries + 1, next_retry_at = ?, error = ?, output = ?
                        WHERE id = ?
                    """, (next_retry_at, error, output, task_id))
            else:
                status = 'completed'
                conn.execute("""
                    UPDATE tasks
                    SET status = ?, completed_at = ?, output = ?, error = ?
                    WHERE id = ?
                """, (status, time.time(), output, error, task_id))

            conn.commit()

    def cancel_task(self, task_id: int):
        with get_db_connection() as conn:
            conn.execute("UPDATE tasks SET status = 'canceled' WHERE id = ?", (task_id,))
            conn.commit()

    def list_tasks(self, job_name: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
        with get_db_connection() as conn:
            query = "SELECT * FROM tasks"
            params = []
            conditions = []
            if job_name:
                conditions.append("job_name = ?")
                params.append(job_name)
            if status:
                conditions.append("status = ?")
                params.append(status)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC"
            cursor = conn.execute(query, params)
            tasks = []
            for row in cursor.fetchall():
                task = dict(row)
                if task['payload']:
                    task['payload'] = json.loads(task['payload'])
                tasks.append(task)
            return tasks

    def purge_old_tasks(self, days: int = 30):
        """Purge completed/failed tasks older than N days"""
        with get_db_connection() as conn:
            cutoff = time.time() - (days * 86400)
            conn.execute("""
                DELETE FROM tasks
                WHERE status IN ('completed', 'failed', 'canceled')
                AND created_at < ?
            """, (cutoff,))
            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        with get_db_connection() as conn:
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM tasks
                GROUP BY status
            """)
            stats = {row['status']: row['count'] for row in cursor.fetchall()}
            return stats

# --- WORKER THREAD ---
class AIOSWorker:
    def __init__(self, queue: AIOSTaskQueue, orchestrator: 'SystemdOrchestrator'):
        self.queue = queue
        self.orchestrator = orchestrator
        self._stop_event = threading.Event()

    def start(self):
        """Start background worker thread"""
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self._stop_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            task = self.queue.get_next_task()
            if not task:
                time.sleep(POLL_INTERVAL)
                continue

            print(f"[AIOS Worker] Executing task {task['id']}: {task['command']}")
            start_time = time.time()
            try:
                # Execute command via shell
                result = subprocess.run(
                    task['command'],
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1hr max
                )
                output = result.stdout
                error = result.stderr if result.returncode != 0 else ""
                self.queue.complete_task(task['id'], output, error)
                print(f"[AIOS Worker] Task {task['id']} completed in {time.time()-start_time:.2f}s")

            except subprocess.TimeoutExpired:
                self.queue.complete_task(task['id'], "", "TIMEOUT: Command exceeded 1 hour")
                print(f"[AIOS Worker] Task {task['id']} timed out")
            except Exception as e:
                self.queue.complete_task(task['id'], "", f"EXCEPTION: {str(e)}")
                print(f"[AIOS Worker] Task {task['id']} exception: {e}")

# --- INTEGRATION WITH SYSTEMD ORCHESTRATOR ---
class AIOSOrchestratorWithQueue(SystemdOrchestrator):
    def __init__(self):
        super().__init__()
        self.queue = AIOSTaskQueue()
        self.worker = AIOSWorker(self.queue, self)
        self.worker_thread = self.worker.start()

    def add_job_with_task(self, name: str, command: str, payload: Optional[Dict] = None, restart: str = "always") -> str:
        """Add systemd job AND enqueue first task"""
        unit_name = self.add_job(name, command, restart)
        self.queue.add_task(name, command, payload)
        return unit_name

    def status(self) -> dict:
        base_status = super().status()
        queue_stats = self.queue.get_stats()
        base_status['_queue'] = queue_stats
        return base_status

    def cleanup(self):
        super().cleanup()
        self.worker.stop()
        # Optionally: DB_PATH.unlink(missing_ok=True)

# --- CLI EXTENSION ---
def main():
    """Extended main with task queue commands"""
    orch = AIOSOrchestratorWithQueue()

    # Add default jobs if not exist
    if "heartbeat" not in orch.jobs:
        orch.add_job_with_task("heartbeat", "while true; do echo Heartbeat; sleep 5; done")
        orch.start_job("heartbeat")
    if "todo_app" not in orch.jobs:
        orch.add_job_with_task("todo_app", f"/usr/bin/python3 {BASE_DIR / 'hybridTODO.py'}")

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "add-task":
            if len(sys.argv) < 4:
                print("Usage: add-task <job_name> <command> [payload_json]")
                return
            job_name = sys.argv[2]
            command = sys.argv[3]
            payload = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
            task_id = orch.queue.add_task(job_name, command, payload)
            print(f"Task {task_id} added for job '{job_name}'")
        elif cmd == "list-tasks":
            job_name = sys.argv[2] if len(sys.argv) > 2 else None
            status = sys.argv[3] if len(sys.argv) > 3 else None
            tasks = orch.queue.list_tasks(job_name, status)
            print(json.dumps(tasks, indent=2, default=str))
        elif cmd == "stats":
            print(json.dumps(orch.queue.get_stats(), indent=2))
        elif cmd == "purge":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            orch.queue.purge_old_tasks(days)
            print(f"Purged tasks older than {days} days")
        else:
            # Delegate to parent
            super_main = SystemdOrchestrator()
            super_main.jobs = orch.jobs  # hacky, but works for CLI
            if cmd == "start":
                for name in orch.jobs:
                    ms = orch.start_job(name)
                    print(f"Started {name} in {ms:.2f}ms")
            elif cmd == "stop":
                for name in orch.jobs:
                    ms = orch.stop_job(name)
                    print(f"Stopped {name} in {ms:.2f}ms")
            elif cmd == "restart":
                times = orch.restart_all()
                print(f"Restart times: {times}")
            elif cmd == "status":
                print(json.dumps(orch.status(), indent=2, default=str))
            elif cmd == "cleanup":
                orch.cleanup()
                print("Cleaned up all units and stopped worker")
            else:
                print(f"Usage: {sys.argv[0]} [start|stop|restart|status|cleanup|add-task|list-tasks|stats|purge]")
    else:
        status = orch.status()
        print(f"=== AIOS Systemd + SQLite Task Queue ===")
        print(f"Jobs: {len(status)-1} | Queue Stats: {status.get('_queue', {})}")
        for name, info in status.items():
            if name != '_queue':
                print(f"  {name}: {info['state']} (PID: {info['pid']})")

if __name__ == "__main__":
    main()