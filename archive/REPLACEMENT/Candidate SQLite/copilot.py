#!/usr/bin/env python3
"""
AIOS SQLite Task Queue

Persistent, atomic, JSON-payload queue for AI workflow orchestrator.
"""

import sqlite3
import uuid
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any

DB_PATH = Path.home() / ".config" / "aios" / "tasks.db"

class SQLiteTaskQueue:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
          id          TEXT PRIMARY KEY,
          payload     TEXT NOT NULL,
          status      TEXT NOT NULL CHECK(status IN ('pending','locked','done')),
          created_at  REAL NOT NULL,
          locked_at   REAL
        )
        """)
        self.conn.commit()

    def enqueue(self, payload: Dict[str, Any]) -> str:
        task_id = str(uuid.uuid4())
        now = time.time()
        self.conn.execute(
            "INSERT INTO tasks (id, payload, status, created_at) VALUES (?, ?, 'pending', ?)",
            (task_id, json.dumps(payload), now)
        )
        self.conn.commit()
        return task_id

    def pop(self, lock_timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        now = time.time()
        cur = self.conn.cursor()
        # release locks older than timeout
        cur.execute(
            "UPDATE tasks SET status='pending', locked_at=NULL "
            "WHERE status='locked' AND locked_at < ?",
            (now - lock_timeout,)
        )
        # claim one pending task
        cur.execute(
            "SELECT id, payload FROM tasks "
            "WHERE status='pending' ORDER BY created_at LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return None

        task_id, payload_json = row
        cur.execute(
            "UPDATE tasks SET status='locked', locked_at=? WHERE id=?",
            (now, task_id)
        )
        self.conn.commit()

        return {"id": task_id, "payload": json.loads(payload_json)}

    def complete(self, task_id: str) -> bool:
        cur = self.conn.execute(
            "UPDATE tasks SET status='done' WHERE id=? AND status='locked'",
            (task_id,)
        )
        self.conn.commit()
        return cur.rowcount == 1

    def purge_done(self) -> int:
        cur = self.conn.execute("DELETE FROM tasks WHERE status='done'")
        self.conn.commit()
        return cur.rowcount

    def pending_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'")
        return cur.fetchone()[0]

    def locked_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM tasks WHERE status='locked'")
        return cur.fetchone()[0]

    def all_status(self) -> Dict[str, int]:
        cur = self.conn.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        )
        return {status: count for status, count in cur.fetchall()}


# Example integration snippet with your existing SystemdOrchestrator

def main():
    queue = SQLiteTaskQueue()
    # Enqueue a demo workflow job
    task_id = queue.enqueue({"action": "run_workflow", "params": {"foo": "bar"}})
    print(f"Enqueued task: {task_id}")

    # Pop & process
    task = queue.pop()
    if task:
        print(f"Processing: {task['id']} -> {task['payload']}")
        # ... invoke SystemdOrchestrator.add_job(...) as needed ...
        # Once done:
        if queue.complete(task["id"]):
            print(f"Completed {task['id']}")
        else:
            print(f"Failed to complete {task['id']}")

    # Report status
    print("Queue stats:", queue.all_status())

if __name__ == "__main__":
    main()
