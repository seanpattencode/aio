#!/usr/bin/env python3
"""
AIOS Orchestrator: Synthesized Production Model
- Uses a high-performance SQLite queue for task state.
- Delegates execution and reaping to systemd via transient units.
"""
import sqlite3
import subprocess
import json
import time
import sys
import os
import signal
import shlex
from pathlib import Path

# --- Configuration ---
DB_PATH = Path(__file__).parent / "aios.db"
UNIT_PREFIX = "aios-task-"

# --- High-Performance SQLite Task Queue ---
class TaskQueue:
    """Manages task state in SQLite using production-grade settings."""
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA busy_timeout=5000;
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                cmd TEXT NOT NULL,
                rt_priority INTEGER DEFAULT 0, -- 0 for non-RT, 1-99 for RT
                status TEXT DEFAULT 'pending', -- pending, running, completed, failed
                created_at INT DEFAULT (strftime('%s', 'now')),
                completed_at INT
            );
            CREATE INDEX IF NOT EXISTS idx_status_prio ON tasks(status, rt_priority DESC, created_at);
        """)

    def add(self, name, cmd, rt_priority=0):
        """Adds a task, returning its ID or None if the name is not unique."""
        try:
            return self.conn.execute(
                "INSERT INTO tasks(name, cmd, rt_priority) VALUES(?,?,?)",
                (name, cmd, rt_priority)
            ).lastrowid
        except sqlite3.IntegrityError:
            print(f"Error: Task name '{name}' already exists.")
            return None

    def get_next(self):
        """Atomically fetches and marks the next task as 'running'."""
        try:
            cursor = self.conn.execute("""
                UPDATE tasks SET status='running' WHERE id = (
                    SELECT id FROM tasks WHERE status='pending'
                    ORDER BY rt_priority DESC, created_at ASC LIMIT 1
                ) RETURNING id, name, cmd, rt_priority
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError: # Fallback for older SQLite
            with self.conn: # Implicit BEGIN/COMMIT
                row = self.conn.execute(
                    "SELECT id, name, cmd, rt_priority FROM tasks WHERE status='pending' "
                    "ORDER BY rt_priority DESC, created_at ASC LIMIT 1"
                ).fetchone()
                if not row: return None
                self.conn.execute("UPDATE tasks SET status='running' WHERE id=?", (row['id'],))
                return dict(row)

    def complete(self, task_id, success):
        """Marks a task as completed or failed."""
        status = 'completed' if success else 'failed'
        self.conn.execute(
            "UPDATE tasks SET status=?, completed_at=strftime('%s', 'now') WHERE id=?",
            (status, task_id)
        )

    def stats(self):
        """Returns a count of tasks by status."""
        return {r['status']: r['count'] for r in
                self.conn.execute("SELECT status, COUNT(*) as count FROM tasks GROUP BY status")}

# --- Systemd Executor for Perfect Reaping ---
class SystemdExecutor:
    """Delegates command execution to transient systemd units."""
    def _run_cmd(self, args):
        return subprocess.run(["systemctl", "--user"] + args, capture_output=True, text=True)

    def run_task(self, name, cmd, rt_priority):
        """Runs a command in a transient .service unit, which guarantees no zombies."""
        unit_name = f"{UNIT_PREFIX}{name.replace(' ', '_')}.service"
        print(f"Executing '{name}' via transient unit '{unit_name}'")

        run_args = ["systemd-run", "--user", "--collect", "--unit", unit_name,
                    "--property=StandardOutput=journal", "--property=StandardError=journal"]
        if rt_priority > 0:
            run_args.extend([f"--property=CPUSchedulingPolicy=rr",
                             f"--property=CPUSchedulingPriority={rt_priority}"])

        proc = subprocess.run(run_args + shlex.split(cmd), capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"Error starting systemd-run for '{name}': {proc.stderr}")
            return False, None
        return True, unit_name

    def is_active(self, unit_name):
        return self._run_cmd(["is-active", unit_name]).returncode == 0

    def get_result(self, unit_name):
        res = self._run_cmd(["show", unit_name, "--property=Result"]).stdout.strip()
        return res.split("=")[1] == "success" if "=" in res else False

# --- Worker & CLI ---
def worker_loop(q, executor):
    """Connects the queue to the executor, managing running tasks."""
    print(f"Worker started (PID: {os.getpid()}). Press Ctrl+C to exit.")
    running_tasks = {}  # {task_id: unit_name}
    shutdown = threading.Event()
    signal.signal(signal.SIGINT, lambda s, f: shutdown.set())
    signal.signal(signal.SIGTERM, lambda s, f: shutdown.set())

    while not shutdown.is_set():
        for task_id, unit_name in list(running_tasks.items()):
            if not executor.is_active(unit_name):
                success = executor.get_result(unit_name)
                print(f"Task {task_id} ('{unit_name}') finished with status: {'SUCCESS' if success else 'FAILURE'}")
                q.complete(task_id, success)
                del running_tasks[task_id]

        if not shutdown.is_set() and (task := q.get_next()):
            success, unit_name = executor.run_task(task['name'], task['cmd'], task['rt_priority'])
            if success:
                running_tasks[task['id']] = unit_name
            else:
                q.complete(task['id'], success=False)

        time.sleep(1) # Poll interval
    print("\nShutdown complete.")

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ["worker", "add", "stats"]:
        print(f"Usage: {sys.argv[0]} <worker|add|stats>", file=sys.stderr)
        sys.exit(1)

    q = TaskQueue()
    cmd = sys.argv[1]

    if cmd == "worker":
        worker_loop(q, SystemdExecutor())
    elif cmd == "add":
        if len(sys.argv) < 4:
            print("Usage: add <name> <command> [--rt priority]", file=sys.stderr)
            sys.exit(1)
        name, command = sys.argv[2], sys.argv[3]
        rt = int(sys.argv[5]) if len(sys.argv) > 4 and sys.argv[4] == '--rt' else 0
        if task_id := q.add(name, command, rt):
            print(f"Added task '{name}' with ID {task_id}.")
    elif cmd == "stats":
        print(json.dumps(q.stats(), indent=2))

if __name__ == "__main__":
    main()