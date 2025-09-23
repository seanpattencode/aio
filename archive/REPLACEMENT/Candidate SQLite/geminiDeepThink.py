#!/usr/bin/env python3
"""
AIOS Task Queue - Robust, Persistent, Concurrent SQLite Implementation
"""

import sqlite3
import json
import time
import logging
import os
import uuid
import random
import sys
from enum import Enum
from typing import Optional, Dict, Any
from pathlib import Path

# Configuration
BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_queue.db"
# Timeout (seconds) before a RUNNING task without a heartbeat is considered crashed/stale
TASK_LEASE_DURATION = 300
POLL_INTERVAL = 5

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] (Worker-%(process)d) %(message)s')
logger = logging.getLogger("AIOSTaskQueue")

class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class AIOSTaskQueue:
    """
    A persistent, process-safe task queue using SQLite, optimized for concurrency.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_type TEXT NOT NULL,
        payload TEXT, -- JSON payload
        priority INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'PENDING',
        
        -- Reliability fields
        attempts INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        error_log TEXT,
        
        -- Timing and Leasing fields (Using REAL for high precision Python time)
        created_at REAL NOT NULL,
        run_after REAL NOT NULL,
        started_at REAL,
        finished_at REAL,
        lease_expires_at REAL -- Heartbeat/Visibility timeout
    );

    -- Index optimized for fetching the next task
    CREATE INDEX IF NOT EXISTS idx_tasks_fetch ON tasks (status, run_after, priority DESC, created_at ASC);
    -- Index for identifying stale tasks
    CREATE INDEX IF NOT EXISTS idx_tasks_stale ON tasks (status, lease_expires_at);
    """

    def __init__(self, db_path: Path = DB_PATH, timeout: int = 30):
        self.db_path = str(db_path)
        self.timeout = timeout
        self._setup_db()

    def _connect(self) -> sqlite3.Connection:
        """Establish a connection. We use a new connection for most operations
           to ensure process safety without complex connection pooling."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=self.timeout)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def _setup_db(self):
        """Initialize the database schema and settings."""
        try:
            with self._connect() as conn:
                # Enable WAL for high concurrency (essential for queues)
                conn.execute("PRAGMA journal_mode=WAL;")
                # Optimize write speed (balance durability and performance)
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.executescript(self.SCHEMA)
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    def enqueue(self, task_type: str, payload: Dict[str, Any], priority: int = 0, delay: float = 0, max_retries: int = 3) -> int:
        """Add a new task to the queue."""
        now = time.time()
        run_after = now + delay
        payload_json = json.dumps(payload)

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO tasks (task_type, payload, priority, max_retries, created_at, run_after)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (task_type, payload_json, priority, max_retries, now, run_after)
                )
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to enqueue task: {e}")
            raise

    def _recover_stale_tasks(self, conn: sqlite3.Connection):
        """Find tasks leased by crashed workers and requeue/fail them."""
        now = time.time()
        
        # Find tasks that are RUNNING but their lease has expired
        cursor = conn.execute(
            """
            SELECT id, attempts, max_retries FROM tasks
            WHERE status = ? AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (TaskStatus.RUNNING.value, now)
        )
        
        stale_tasks = cursor.fetchall()
        if not stale_tasks:
            return

        for task in stale_tasks:
            logger.warning(f"Recovering stale task {task['id']}")
            # The attempt that crashed counts, so we use the current 'attempts' value for backoff calculation
            status, next_run = self._calculate_retry(task['attempts'], task['max_retries'], now)
            
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, run_after = ?, lease_expires_at = NULL, started_at = NULL,
                    error_log = COALESCE(error_log, '') || ?
                WHERE id = ?
                """,
                (status.value, next_run, f"\n[{now}] Task lease expired (Worker crash suspected).", task['id'])
            )

    def dequeue(self) -> Optional[Dict[str, Any]]:
        """
        Atomically claim the next available task.
        Uses UPDATE...RETURNING for optimal performance and safety.
        """
        now = time.time()
        lease_expires = now + TASK_LEASE_DURATION

        try:
            with self._connect() as conn:
                # 1. Handle any stalled tasks before fetching new ones (done in transaction)
                self._recover_stale_tasks(conn)
                
                # 2. Atomically find, update, and return the next task
                cursor = conn.execute(
                    """
                    UPDATE tasks
                    SET
                        status = ?,
                        lease_expires_at = ?,
                        started_at = ?,
                        attempts = attempts + 1
                    WHERE id = (
                        -- Subquery to find the highest priority, oldest available task
                        SELECT id
                        FROM tasks
                        WHERE status = ? AND run_after <= ?
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                    )
                    RETURNING *;
                    """,
                    (TaskStatus.RUNNING.value, lease_expires, now, TaskStatus.PENDING.value, now)
                )

                task_data = cursor.fetchone()

                if task_data:
                    return self._deserialize_task(task_data)
            return None

        except sqlite3.OperationalError as e:
            # Handle potential database locks gracefully
            if "database is locked" in str(e):
                logger.warning("Database locked during dequeue, skipping cycle.")
                return None
            raise

    def _deserialize_task(self, task_row: sqlite3.Row) -> Dict[str, Any]:
        task = dict(task_row)
        try:
            task['payload'] = json.loads(task['payload'])
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Corrupt payload for task {task['id']}")
            task['payload'] = {} # Prevent crash on access
        return task

    def heartbeat(self, task_id: int):
        """Extend the lease on a running task."""
        now = time.time()
        lease_expires = now + TASK_LEASE_DURATION
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE tasks SET lease_expires_at = ? WHERE id = ?",
                    (lease_expires, task_id)
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to send heartbeat for task {task_id}: {e}")

    def _calculate_retry(self, attempts: int, max_retries: int, now: float) -> Tuple[TaskStatus, float]:
        """Determine next status and run time based on retry policy."""
        if attempts < max_retries:
            # Exponential backoff (2^attempts seconds) + jitter
            backoff = (2 ** attempts) + random.uniform(0, 2)
            next_run = now + backoff
            return TaskStatus.PENDING, next_run
        else:
            return TaskStatus.FAILED, now

    def finalize_task(self, task_id: int, success: bool, result_message: str = ""):
        """Mark a task as completed or failed, handling retries."""
        now = time.time()
        try:
            with self._connect() as conn:
                if success:
                    conn.execute(
                        """
                        UPDATE tasks SET status = ?, finished_at = ?, lease_expires_at = NULL
                        WHERE id = ?
                        """,
                        (TaskStatus.COMPLETED.value, now, task_id)
                    )
                else:
                    # Handle failure
                    task = conn.execute("SELECT attempts, max_retries FROM tasks WHERE id = ?", (task_id,)).fetchone()
                    if not task:
                        return

                    status, next_run = self._calculate_retry(task['attempts'], task['max_retries'], now)
                    
                    log_entry = f"\n[{now}] Attempt {task['attempts']} failed: {result_message}"

                    conn.execute(
                        """
                        UPDATE tasks
                        SET status = ?, run_after = ?, finished_at = ?, lease_expires_at = NULL, started_at = NULL,
                            error_log = COALESCE(error_log, '') || ?
                        WHERE id = ?
                        """,
                        (status.value, next_run, (now if status == TaskStatus.FAILED else None), log_entry, task_id)
                    )
        except sqlite3.Error as e:
            logger.error(f"Failed to finalize task {task_id}: {e}")


# --- AIOS Worker Implementation ---
# This section defines the worker process managed by SystemdOrchestrator.

def process_task(task: Dict[str, Any], queue: AIOSTaskQueue):
    """Executes the AI workflow logic."""
    task_id = task['id']
    # Attempts count starts at 1
    logger.info(f"Processing Task {task_id} (Type: {task['task_type']}, Attempt: {task['attempts']})")
    
    try:
        # --- Replace with actual AI workflow execution ---
        payload = task['payload']
        
        # Simulate work and send heartbeats for long processes
        for i in range(3):
            time.sleep(1)
            queue.heartbeat(task_id)
            
        # Simulate failure based on payload for testing
        if payload.get("action") == "fail_test" and task['attempts'] < task['max_retries']:
             raise RuntimeError("Simulated task failure for retry testing.")

        # -------------------------------------------------
        
        queue.finalize_task(task_id, success=True)
        logger.info(f"Completed task {task_id}")

    except Exception as e:
        logger.error(f"Error processing task {task_id}: {e}")
        queue.finalize_task(task_id, success=False, result_message=str(e))

def worker_loop():
    """The main loop for a worker process."""
    queue = AIOSTaskQueue()
    logger.info("AIOS Worker started. Polling for tasks...")

    while True:
        try:
            task = queue.dequeue()
            if task:
                process_task(task, queue)
            else:
                # No tasks available, sleep to prevent busy-waiting.
                # Recovery of stale tasks happens during the next dequeue attempt.
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Worker shutting down gracefully.")
            break
        except Exception as e:
            # Catch unexpected errors to ensure stability and prevent rapid systemd restarts
            logger.critical(f"Fatal error in worker loop: {e}", exc_info=True)
            time.sleep(15)

if __name__ == "__main__":
    # CLI interface for management and running the worker
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        queue = AIOSTaskQueue()

        if cmd == "work":
            # This is the command SystemdOrchestrator runs:
            # Example: orch.add_job("aios_worker", f"/usr/bin/python3 {__file__} work")
            worker_loop()
        
        elif cmd == "enqueue":
            # Example: python3 aios_queue.py enqueue AI_PROCESSING '{"data": "test"}' 5
            if len(sys.argv) < 4:
                print("Usage: enqueue <task_type> <payload_json> [priority=0]")
                sys.exit(1)
            task_type = sys.argv[2]
            payload_str = sys.argv[3]
            priority = int(sys.argv[4]) if len(sys.argv) > 4 else 0
            try:
                payload = json.loads(payload_str)
                task_id = queue.enqueue(task_type, payload, priority=priority)
                print(f"Enqueued task ID: {task_id}")
            except json.JSONDecodeError:
                print("Invalid JSON payload.")
                sys.exit(1)
        elif cmd == "add_test":
             queue.enqueue("test_high_prio", {"data": "important"}, priority=10)
             queue.enqueue("test_low_prio", {"data": "background"}, priority=0)
             queue.enqueue("test_fail", {"action": "fail_test"}, priority=5, max_retries=3)
             print("Added test tasks.")
    else:
        print(f"Usage: {sys.argv[0]} [work|enqueue|add_test]")