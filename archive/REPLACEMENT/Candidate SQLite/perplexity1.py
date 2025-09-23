import sqlite3
import threading
import time
import datetime
import json

class SQLiteTaskQueue:
    def __init__(self, path="aios_queue.db"):
        self.path = path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path, isolation_level="IMMEDIATE")

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                args TEXT,
                queue TEXT DEFAULT 'default',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                next_execution_at DATETIME,
                last_executed_at DATETIME,
                attempts INTEGER DEFAULT 0,
                state TEXT DEFAULT 'waiting',
                error TEXT,
                reserved_by TEXT
            )""")
            conn.commit()

    def enqueue(self, name: str, args=None, delay_s=0):
        args_json = json.dumps(args or {})
        next_exec = None
        if delay_s:
            next_exec = (datetime.datetime.utcnow() + datetime.timedelta(seconds=delay_s)).isoformat()
        with self._connect() as conn:
            conn.execute("""
            INSERT INTO jobs (name, args, next_execution_at)
            VALUES (?, ?, ?)
            """, (name, args_json, next_exec))
            conn.commit()

    def reserve_job(self, worker_id):
        now = datetime.datetime.utcnow().isoformat()
        with self._connect() as conn:
            cursor = conn.execute("""
            UPDATE jobs SET state='executing', reserved_by=?, last_executed_at=?
            WHERE id=(
                SELECT id FROM jobs
                WHERE state = 'waiting'
                  AND (next_execution_at IS NULL OR next_execution_at <= ?)
                ORDER BY created_at ASC
                LIMIT 1
            )
            RETURNING id, name, args
            """, (worker_id, now, now))
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "name": row[1], "args": json.loads(row[2])}
        return None

    def complete(self, job_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            conn.commit()

    def fail(self, job_id, error):
        with self._connect() as conn:
            conn.execute("""
                UPDATE jobs SET state='failed', error=? WHERE id=?""",
                (str(error), job_id))
            conn.commit()

    def count_pending(self):
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM jobs WHERE state='waiting'")
            return cursor.fetchone()[0]

    def get_all_jobs(self):
        with self._connect() as conn:
            cursor = conn.execute("SELECT id, name, args, state FROM jobs")
            return cursor.fetchall()
