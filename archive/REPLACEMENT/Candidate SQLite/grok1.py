import os
import sqlite3
import json
import time
import threading
import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

class SQLiteTaskQueue:
    """
    Synthesized SQLite-based persistent task queue for AIOS.
    Features: FIFO, thread-safe, ACK (to handle crashes), WAL for speed, prune done tasks.
    Tasks are JSON-serializable dicts for AI workflows.
    <250 lines total.
    """
    _TABLE_NAME = 'aios_tasks'
    _DB_FILE = 'aios_queue.db'  # Single DB as required

    def __init__(self, db_path: str = '.', maxsize: Optional[int] = None, timeout: float = 10.0):
        """
        Initialize queue.
        :param db_path: Directory for DB file.
        :param maxsize: Optional max tasks (raises Full if exceeded).
        :param timeout: DB timeout for locks.
        """
        self.db_path = os.path.join(db_path, self._DB_FILE)
        self.maxsize = maxsize
        self.timeout = timeout
        self.lock = threading.Lock()  # For thread-safety
        self._conn = self._create_connection()
        self._create_table()

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.timeout, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")  # Better performance
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _create_table(self):
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task JSON,
                in_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                lock_time TIMESTAMP,
                done_time TIMESTAMP,
                status TEXT DEFAULT 'ready'  -- 'ready', 'locked', 'done', 'failed'
            );
        """)
        if self.maxsize is not None:
            self._conn.execute(f"""
                CREATE TRIGGER IF NOT EXISTS maxsize_trigger
                BEFORE INSERT ON {self._TABLE_NAME}
                WHEN (SELECT COUNT(*) FROM {self._TABLE_NAME} WHERE done_time IS NULL) >= {self.maxsize}
                BEGIN
                    SELECT RAISE(FAIL, 'Queue full');
                END;
            """)
        self._conn.commit()

    def put(self, task: Dict[str, Any]):
        """
        Enqueue a task (JSON-serializable dict).
        """
        with self.lock:
            try:
                task_json = json.dumps(task)
                with self._conn:
                    self._conn.execute(
                        f"INSERT INTO {self._TABLE_NAME} (task, status) VALUES (?, 'ready')",
                        (task_json,)
                    )
            except sqlite3.IntegrityError as e:
                if 'full' in str(e):
                    raise Full("Queue is full")
                raise

    def get(self) -> Optional[Dict[str, Any]]:
        """
        Get next ready task and lock it. Returns None if empty.
        """
        with self.lock:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(
                    f"""
                    UPDATE {self._TABLE_NAME}
                    SET lock_time = CURRENT_TIMESTAMP, status = 'locked'
                    WHERE id = (SELECT id FROM {self._TABLE_NAME} WHERE status = 'ready' ORDER BY id LIMIT 1)
                    RETURNING id, task
                    """
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                task_id, task_json = row
                return {'id': task_id, 'task': json.loads(task_json)}

    def ack(self, task_id: int, failed: bool = False, reason: str = ''):
        """
        Acknowledge task as done or failed.
        """
        with self.lock:
            status = 'failed' if failed else 'done'
            with self._conn:
                self._conn.execute(
                    f"UPDATE {self._TABLE_NAME} SET done_time = CURRENT_TIMESTAMP, status = ? WHERE id = ?",
                    (status, task_id)
                )

    def prune(self):
        """
        Remove completed tasks to free space.
        """
        with self.lock:
            with self._conn:
                self._conn.execute(f"DELETE FROM {self._TABLE_NAME} WHERE status IN ('done', 'failed')")

    def qsize(self) -> int:
        """
        Number of pending tasks (ready or locked).
        """
        with self.lock:
            cursor = self._conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {self._TABLE_NAME} WHERE done_time IS NULL")
            return cursor.fetchone()[0]

    def status(self) -> Dict[str, int]:
        """
        Get counts by status.
        """
        with self.lock:
            cursor = self._conn.cursor()
            cursor.execute(f"SELECT status, COUNT(*) FROM {self._TABLE_NAME} GROUP BY status")
            return dict(cursor.fetchall())

    def vacuum(self):
        """
        Optimize DB (run periodically).
        """
        with self.lock:
            self._conn.execute("VACUUM;")
            self._conn.commit()

    def close(self):
        self._conn.close()

# Example integration with your SystemdOrchestrator (add this to your script):
# queue = SQLiteTaskQueue(BASE_DIR)
# # Enqueue example AI workflow task
# queue.put({'workflow': 'generate_plan', 'user': 'test', 'details': 'Build AI app'})
# # Add a worker job
# if "queue_worker" not in orch.jobs:
#     worker_cmd = f"/usr/bin/python3 -c \"from your_script import SQLiteTaskQueue; q = SQLiteTaskQueue('{BASE_DIR}'); while True: task = q.get(); if task: process(task['task']); q.ack(task['id']); time.sleep(1)\""
#     orch.add_job("queue_worker", worker_cmd)
#     orch.start_job("queue_worker")
# # Where 'process' is your function to run/review AI workflow steps.