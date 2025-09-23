#!/usr/bin/env python3
"""
ClaudeCode2: Advanced Scheduling and Job Queue with ACK Support
Includes delayed execution, exponential backoff, dependency tracking, and worker pools
"""

import os
import sys
import time
import sqlite3
import json
import subprocess
import threading
import signal
import logging
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aios_scheduler")

BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_scheduler.db"
UNIT_PREFIX = "aios-"

class TaskStatus(Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Task:
    id: int
    name: str
    command: str
    args: Dict[str, Any]
    priority: int
    status: TaskStatus
    unique_key: Optional[str]
    not_before: datetime
    lease_until: Optional[datetime]
    worker_id: Optional[str]
    attempts: int
    max_retries: int
    backoff_ms: int
    created_at: datetime
    updated_at: datetime
    parent_ids: List[int] = None

class AdvancedTaskQueue:
    """Production-grade task queue with scheduling and acknowledgment"""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """Connection with production settings"""
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=30000000000")  # 30GB mmap
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Create advanced schema with dependencies and scheduling"""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    args TEXT DEFAULT '{}',
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'queued',
                    unique_key TEXT,
                    not_before INTEGER DEFAULT 0,
                    lease_until INTEGER,
                    worker_id TEXT,
                    attempts INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    backoff_ms INTEGER DEFAULT 1000,
                    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                    updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                    completed_at INTEGER,
                    error TEXT,
                    result TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_key
                    ON tasks(unique_key)
                    WHERE unique_key IS NOT NULL AND status IN ('queued', 'leased', 'running');

                CREATE INDEX IF NOT EXISTS idx_ready
                    ON tasks(status, priority DESC, not_before, id)
                    WHERE status = 'queued';

                CREATE INDEX IF NOT EXISTS idx_lease
                    ON tasks(lease_until)
                    WHERE status = 'leased';

                CREATE TABLE IF NOT EXISTS task_deps (
                    child_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    parent_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    PRIMARY KEY (child_id, parent_id)
                );

                CREATE TABLE IF NOT EXISTS task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    worker_id TEXT NOT NULL,
                    started_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
                    ended_at INTEGER,
                    exit_code INTEGER,
                    stdout TEXT,
                    stderr TEXT
                );
            """)

    def enqueue(self, name: str, command: str, args: Dict = None,
               priority: int = 0, delay_seconds: float = 0,
               unique_key: str = None, max_retries: int = 3,
               backoff_ms: int = 1000, parent_ids: List[int] = None) -> Optional[int]:
        """Enqueue task with advanced options"""
        args = args or {}
        not_before = int((time.time() + delay_seconds) * 1000)

        with self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Check unique constraint
                if unique_key:
                    cursor = conn.execute("""
                        SELECT id FROM tasks
                        WHERE unique_key = ? AND status IN ('queued', 'leased', 'running')
                    """, (unique_key,))
                    if cursor.fetchone():
                        conn.execute("ROLLBACK")
                        return None

                # Insert task
                cursor = conn.execute("""
                    INSERT INTO tasks (name, command, args, priority, unique_key,
                                     not_before, max_retries, backoff_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, command, json.dumps(args), priority, unique_key,
                     not_before, max_retries, backoff_ms))

                task_id = cursor.lastrowid

                # Add dependencies
                if parent_ids:
                    for parent_id in parent_ids:
                        conn.execute("""
                            INSERT INTO task_deps (child_id, parent_id)
                            VALUES (?, ?)
                        """, (task_id, parent_id))

                conn.execute("COMMIT")
                return task_id

            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Enqueue failed: {e}")
                raise

    def claim_tasks(self, worker_id: str, limit: int = 1, lease_seconds: int = 300) -> List[Task]:
        """Claim tasks atomically with lease"""
        now_ms = int(time.time() * 1000)
        lease_until = now_ms + (lease_seconds * 1000)

        with self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Find eligible tasks (dependencies met)
                cursor = conn.execute("""
                    SELECT t.id FROM tasks t
                    WHERE t.status = 'queued'
                    AND t.not_before <= ?
                    AND NOT EXISTS (
                        SELECT 1 FROM task_deps d
                        JOIN tasks p ON p.id = d.parent_id
                        WHERE d.child_id = t.id
                        AND p.status != 'succeeded'
                    )
                    ORDER BY t.priority DESC, t.id ASC
                    LIMIT ?
                """, (now_ms, limit))

                task_ids = [row[0] for row in cursor.fetchall()]

                if not task_ids:
                    conn.execute("COMMIT")
                    return []

                # Claim tasks
                placeholders = ','.join('?' * len(task_ids))
                conn.execute(f"""
                    UPDATE tasks
                    SET status = 'leased',
                        lease_until = ?,
                        worker_id = ?,
                        updated_at = ?
                    WHERE id IN ({placeholders})
                """, [lease_until, worker_id, now_ms] + task_ids)

                # Fetch claimed tasks
                cursor = conn.execute(f"""
                    SELECT * FROM tasks WHERE id IN ({placeholders})
                """, task_ids)

                tasks = [self._row_to_task(row) for row in cursor.fetchall()]

                conn.execute("COMMIT")
                return tasks

            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Claim failed: {e}")
                return []

    def start_task(self, task_id: int, worker_id: str) -> int:
        """Mark task as running and create run record"""
        with self._get_conn() as conn:
            now_ms = int(time.time() * 1000)
            conn.execute("""
                UPDATE tasks
                SET status = 'running',
                    attempts = attempts + 1,
                    updated_at = ?
                WHERE id = ? AND status = 'leased'
            """, (now_ms, task_id))

            cursor = conn.execute("""
                INSERT INTO task_runs (task_id, worker_id)
                VALUES (?, ?)
            """, (task_id, worker_id))

            return cursor.lastrowid

    def complete_task(self, task_id: int, run_id: int, success: bool,
                     exit_code: int = 0, stdout: str = "", stderr: str = ""):
        """Complete or fail task with exponential backoff"""
        with self._get_conn() as conn:
            now_ms = int(time.time() * 1000)

            # Update run record
            conn.execute("""
                UPDATE task_runs
                SET ended_at = ?, exit_code = ?, stdout = ?, stderr = ?
                WHERE id = ?
            """, (now_ms, exit_code, stdout[:10000], stderr[:10000], run_id))

            if success:
                # Mark as succeeded
                conn.execute("""
                    UPDATE tasks
                    SET status = 'succeeded',
                        completed_at = ?,
                        updated_at = ?,
                        lease_until = NULL,
                        worker_id = NULL
                    WHERE id = ?
                """, (now_ms, now_ms, task_id))
            else:
                # Check retry eligibility
                cursor = conn.execute("""
                    SELECT attempts, max_retries, backoff_ms
                    FROM tasks WHERE id = ?
                """, (task_id,))
                row = cursor.fetchone()

                if row['attempts'] < row['max_retries']:
                    # Calculate exponential backoff with jitter
                    delay_ms = min(row['backoff_ms'] * (2 ** row['attempts']), 3600000)  # Cap at 1 hour
                    jitter = int(delay_ms * 0.1)  # 10% jitter
                    not_before = now_ms + delay_ms + (hash(task_id) % jitter)

                    conn.execute("""
                        UPDATE tasks
                        SET status = 'queued',
                            not_before = ?,
                            lease_until = NULL,
                            worker_id = NULL,
                            updated_at = ?
                        WHERE id = ?
                    """, (not_before, now_ms, task_id))
                else:
                    # Permanently failed
                    conn.execute("""
                        UPDATE tasks
                        SET status = 'failed',
                            completed_at = ?,
                            updated_at = ?,
                            error = ?,
                            lease_until = NULL,
                            worker_id = NULL
                        WHERE id = ?
                    """, (now_ms, now_ms, stderr[:1000], task_id))

    def reclaim_expired_leases(self) -> int:
        """Reclaim tasks with expired leases"""
        now_ms = int(time.time() * 1000)
        with self._get_conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks
                SET status = 'queued',
                    lease_until = NULL,
                    worker_id = NULL,
                    updated_at = ?
                WHERE status = 'leased' AND lease_until < ?
            """, (now_ms, now_ms))
            return cursor.rowcount

    def _row_to_task(self, row) -> Task:
        """Convert row to Task object"""
        return Task(
            id=row['id'],
            name=row['name'],
            command=row['command'],
            args=json.loads(row['args']),
            priority=row['priority'],
            status=TaskStatus(row['status']),
            unique_key=row['unique_key'],
            not_before=datetime.fromtimestamp(row['not_before'] / 1000),
            lease_until=datetime.fromtimestamp(row['lease_until'] / 1000) if row['lease_until'] else None,
            worker_id=row['worker_id'],
            attempts=row['attempts'],
            max_retries=row['max_retries'],
            backoff_ms=row['backoff_ms'],
            created_at=datetime.fromtimestamp(row['created_at'] / 1000),
            updated_at=datetime.fromtimestamp(row['updated_at'] / 1000)
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get detailed statistics"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM tasks
                GROUP BY status
            """)
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            cursor = conn.execute("""
                SELECT COUNT(*) as expired
                FROM tasks
                WHERE status = 'leased' AND lease_until < ?
            """, (int(time.time() * 1000),))
            expired = cursor.fetchone()['expired']

            return {**status_counts, 'expired_leases': expired}

class Worker:
    """Advanced worker with graceful shutdown and lease management"""

    def __init__(self, queue: AdvancedTaskQueue, worker_id: str = None):
        self.queue = queue
        self.worker_id = worker_id or f"worker-{os.getpid()}"
        self.running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        """Graceful shutdown"""
        logger.info(f"Worker {self.worker_id} shutting down...")
        self.running = False

    def run(self, batch_size: int = 1, lease_seconds: int = 300):
        """Main worker loop"""
        logger.info(f"Worker {self.worker_id} started (batch_size={batch_size})")

        while self.running:
            try:
                # Reclaim expired leases periodically
                reclaimed = self.queue.reclaim_expired_leases()
                if reclaimed:
                    logger.info(f"Reclaimed {reclaimed} expired leases")

                # Claim tasks
                tasks = self.queue.claim_tasks(self.worker_id, batch_size, lease_seconds)

                for task in tasks:
                    if not self.running:
                        break

                    logger.info(f"Executing task {task.id}: {task.name}")
                    run_id = self.queue.start_task(task.id, self.worker_id)

                    try:
                        # Execute command
                        result = subprocess.run(
                            task.command,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=lease_seconds - 10  # Leave margin for cleanup
                        )

                        self.queue.complete_task(
                            task.id, run_id,
                            result.returncode == 0,
                            result.returncode,
                            result.stdout, result.stderr
                        )

                        status = "succeeded" if result.returncode == 0 else "failed"
                        logger.info(f"Task {task.id} {status} (exit={result.returncode})")

                    except subprocess.TimeoutExpired:
                        self.queue.complete_task(task.id, run_id, False, -1, "", "TIMEOUT")
                        logger.warning(f"Task {task.id} timed out")

                    except Exception as e:
                        self.queue.complete_task(task.id, run_id, False, -1, "", str(e))
                        logger.error(f"Task {task.id} error: {e}")

                if not tasks:
                    time.sleep(1)  # No tasks available

            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(5)

        logger.info(f"Worker {self.worker_id} stopped")

def main():
    """CLI interface"""
    if len(sys.argv) < 2:
        print("Usage: claudeCode2.py <command> [args...]")
        print("Commands: enqueue, worker, stats, test")
        sys.exit(1)

    queue = AdvancedTaskQueue()
    cmd = sys.argv[1]

    if cmd == "enqueue":
        if len(sys.argv) < 4:
            print("Usage: enqueue <name> <command> [options]")
            sys.exit(1)

        task_id = queue.enqueue(
            name=sys.argv[2],
            command=sys.argv[3],
            priority=int(sys.argv[4]) if len(sys.argv) > 4 else 0,
            delay_seconds=float(sys.argv[5]) if len(sys.argv) > 5 else 0
        )
        print(f"Enqueued task {task_id}")

    elif cmd == "worker":
        batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        worker = Worker(queue)
        worker.run(batch_size)

    elif cmd == "stats":
        stats = queue.get_stats()
        print(json.dumps(stats, indent=2))

    elif cmd == "test":
        # Test workflow with dependencies
        print("Creating test workflow...")

        # Parent task
        parent_id = queue.enqueue("setup", "echo 'Setting up...'", priority=10)
        print(f"Parent task: {parent_id}")

        # Child tasks with dependency
        for i in range(3):
            child_id = queue.enqueue(
                f"process_{i}",
                f"echo 'Processing item {i}'",
                priority=5,
                parent_ids=[parent_id]
            )
            print(f"Child task {i}: {child_id}")

        # Delayed task
        delayed_id = queue.enqueue(
            "cleanup",
            "echo 'Cleaning up...'",
            delay_seconds=5,
            unique_key="cleanup_job"
        )
        print(f"Delayed task: {delayed_id}")

        print("\nRun 'worker' command to process tasks")

    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()