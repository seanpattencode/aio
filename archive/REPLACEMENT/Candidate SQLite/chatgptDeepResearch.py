import sqlite3
import json
import os

class AiosTaskQueue:
    """SQLite-backed task queue for AIOS orchestrator."""
    def __init__(self, db_path="~/.aios_tasks.db"):
        self.db_path = os.path.expanduser(db_path)
        # Connect to SQLite database (enable WAL for concurrent readers/writers)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.row_factory = sqlite3.Row  # Access columns by name
        # Create tasks table if not exists
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,               -- Task name/description
            command     TEXT,               -- Command or script to execute
            data        TEXT,               -- JSON-encoded extra data (args, etc.)
            status      TEXT DEFAULT 'PENDING', -- 'PENDING','APPROVED','REJECTED','RUNNING','DONE'
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self.conn.commit()
    
    def add_task(self, name, command, data=None):
        """Add a new task to the queue (initially PENDING review)."""
        payload = json.dumps(data) if data is not None else None
        cur = self.conn.cursor()
        cur.execute("INSERT INTO tasks (name, command, data, status) VALUES (?, ?, ?, 'PENDING');",
                    (name, command, payload))
        self.conn.commit()
        task_id = cur.lastrowid
        cur.close()
        return task_id
    
    def list_tasks(self, status=None):
        """List tasks, optionally filtered by status."""
        cur = self.conn.cursor()
        if status:
            cur.execute("SELECT * FROM tasks WHERE status=? ORDER BY id;", (status,))
        else:
            cur.execute("SELECT * FROM tasks ORDER BY id;")
        tasks = [dict(row) for row in cur.fetchall()]
        cur.close()
        return tasks
    
    def approve_task(self, task_id):
        """Mark a PENDING task as APPROVED (user accepts the task)."""
        cur = self.conn.cursor()
        cur.execute("UPDATE tasks SET status='APPROVED' WHERE id=? AND status='PENDING';", (task_id,))
        changed = (cur.rowcount > 0)
        self.conn.commit()
        cur.close()
        return changed
    
    def reject_task(self, task_id):
        """Mark a PENDING task as REJECTED."""
        cur = self.conn.cursor()
        cur.execute("UPDATE tasks SET status='REJECTED' WHERE id=? AND status='PENDING';", (task_id,))
        changed = (cur.rowcount > 0)
        self.conn.commit()
        cur.close()
        return changed
    
    def fetch_next_task(self):
        """Atomically retrieve and remove the next APPROVED task (FIFO order)."""
        cur = self.conn.cursor()
        # Use a transaction to avoid race conditions
        self.conn.execute("BEGIN IMMEDIATE;")  # Lock for writing
        cur.execute("SELECT id, name, command, data FROM tasks WHERE status='APPROVED' ORDER BY id LIMIT 1;")
        row = cur.fetchone()
        if not row:
            # No approved tasks available
            self.conn.execute("ROLLBACK;")
            cur.close()
            return None
        task = dict(row)
        # Delete the task we fetched (mark it as taken)
        cur.execute("DELETE FROM tasks WHERE id=?;", (task["id"],))
        self.conn.commit()  # Releases the lock
        cur.close()
        # Parse JSON data if present
        if task.get("data"):
            task["data"] = json.loads(task["data"])
        return task
    
    def mark_task_done(self, task_id, success=True):
        """Mark a running task as done (for logging/completion tracking)."""
        status = 'DONE' if success else 'FAILED'
        cur = self.conn.cursor()
        cur.execute("UPDATE tasks SET status=? WHERE id=?;", (status, task_id))
        self.conn.commit()
        cur.close()
    
    def close(self):
        """Close the database connection."""
        self.conn.close()

# Example usage with the SystemdOrchestrator from AIOS
if __name__ == "__main__":
    queue = AiosTaskQueue("~/.config/aios/aios_tasks.db")
    orch = SystemdOrchestrator()  # from AIOS orchestrator code
    
    # 1. Enqueue a new AI task (PENDING user review)
    task_id = queue.add_task("example-task", "/usr/bin/python3 myscript.py --foo bar")
    print(f"Task {task_id} enqueued for review.")
    
    # 2. List pending tasks (for an admin UI or CLI to review)
    pending = queue.list_tasks(status="PENDING")
    print(f"Pending tasks: {pending}")
    
    # 3. Simulate user accepting the task
    queue.approve_task(task_id)
    
    # 4. Orchestrator fetches and runs the next approved task
    task = queue.fetch_next_task()
    if task:
        print(f"Starting approved task {task['id']}: {task['command']}")
        unit_name = orch.add_job(f"task_{task['id']}", task["command"], restart="no")
        orch.start_job(f"task_{task['id']}")
        queue.mark_task_done(task["id"], success=True)
