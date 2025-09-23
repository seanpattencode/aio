#!/usr/bin/env python3
"""
AIOS Task Orchestrator: Synthesized Production Model
- Uses SQLite for task state management (high-performance WAL mode).
- Delegates all execution and process reaping to systemd for robustness.
- Combines minimalism and production-grade patterns.
"""
import sqlite3
import subprocess
import json
import time
import sys
import os
import signal
from pathlib import Path

# --- Configuration ---
DB_PATH = Path(__file__).parent / "aios.db"
UNIT_PREFIX = "aios-task-"

# --- SQLite Queue (`claudeCodeC` minimalism) ---
class TaskQueue:
    """Manages task state in SQLite using high-performance settings."""
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
                priority INT DEFAULT 0,
                status TEXT DEFAULT 'pending', -- pending, running, completed, failed
                created_at INT DEFAULT (strftime('%s', 'now')),
                completed_at INT
            );
            CREATE INDEX IF NOT EXISTS idx_status_priority
            ON tasks(status, priority DESC, created_at);
        """)

    def add(self, name, cmd, priority=0):
        """Add a new task. Returns its ID or None if the name is not unique."""
        try:
            return self.conn.execute(
                "INSERT INTO tasks(name, cmd, priority) VALUES(?,?,?)",
                (name, cmd, priority)
            ).lastrowid
        except sqlite3.IntegrityError:
            print(f"Error: Task name '{name}' already exists.")
            return None

    def get_next(self):
        """Atomically fetch and mark the next pending task as 'running'."""
        # The 'UPDATE...RETURNING' is the most atomic and performant way to pop.
        # This avoids race conditions between workers.
        try:
            cursor = self.conn.execute("""
                UPDATE tasks SET status='running' WHERE id = (
                    SELECT id FROM tasks WHERE status='pending'
                    ORDER BY priority DESC, created_at ASC LIMIT 1
                ) RETURNING id, name, cmd
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError: # Fallback for older SQLite versions
            with self.conn:
                row = self.conn.execute(
                    "SELECT id, name, cmd FROM tasks WHERE status='pending' "
                    "ORDER BY priority DESC, created_at ASC LIMIT 1"
                ).fetchone()
                if not row: return None
                self.conn.execute("UPDATE tasks SET status='running' WHERE id=?", (row['id'],))
                return dict(row)


    def complete(self, task_id, success):
        """Mark a task as completed or failed."""
        status = 'completed' if success else 'failed'
        self.conn.execute(
            "UPDATE tasks SET status=?, completed_at=strftime('%s', 'now') WHERE id=?",
            (status, task_id)
        )

    def stats(self):
        """Return a count of tasks by status."""
        return {
            row['status']: row['count'] for row in
            self.conn.execute("SELECT status, COUNT(*) as count FROM tasks GROUP BY status")
        }

# --- Systemd Executor ---
class SystemdExecutor:
    """Delegates command execution to transient systemd units."""
    def _run_cmd(self, *args):
        return subprocess.run(["systemctl", "--user"] + list(args), capture_output=True, text=True)

    def run_task(self, name, cmd):
        """
        Runs a command in a transient .service unit.
        This is the core pattern: systemd handles logging, cgroups, and cleanup.
        The unit is automatically discarded after it stops.
        """
        unit_name = f"{UNIT_PREFIX}{name}.service"
        print(f"Executing task '{name}' via transient unit '{unit_name}'")
        # Using --no-block will start the unit and return immediately.
        # `systemd-run` is the ideal tool for this pattern.
        proc = self._run_cmd(
            "start",
            "--no-block",
            "--unit", unit_name,
            "--property=StandardOutput=journal",
            "--property=StandardError=journal",
            "/bin/sh", "-c", cmd
        )
        return proc.returncode == 0, unit_name

    def is_active(self, unit_name):
        """Check if the transient unit is still running."""
        proc = self._run_cmd("is-active", unit_name)
        return proc.returncode == 0 # is-active returns 0 if active

    def get_result(self, unit_name):
        """Get the result ('success' or 'failed') of a completed unit."""
        proc = self._run_cmd("show", unit_name, "--property=Result")
        if proc.stdout.strip():
            return proc.stdout.strip().split("=")[1] == "success"
        return False # Assume failure if result isn't found

# --- Worker Loop ---
def worker_loop(q, executor):
    """The main worker loop connecting the queue to the executor."""
    print(f"Worker started (PID: {os.getpid()}). Waiting for tasks...")
    running_tasks = {} # {task_id: unit_name}
    shutdown = threading.Event()

    def handle_signal(*_):
        print("\nShutdown signal received. Finishing running tasks...")
        shutdown.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while not shutdown.is_set():
        # Check status of ongoing tasks
        for task_id, unit_name in list(running_tasks.items()):
            if not executor.is_active(unit_name):
                success = executor.get_result(unit_name)
                status_str = "SUCCESS" if success else "FAILURE"
                print(f"Task {task_id} ('{unit_name}') finished with status: {status_str}")
                q.complete(task_id, success)
                del running_tasks[task_id]

        # Fetch new tasks if not shutting down
        if not shutdown.is_set():
            task = q.get_next()
            if task:
                success, unit_name = executor.run_task(task['name'], task['cmd'])
                if success:
                    running_tasks[task['id']] = unit_name
                else:
                    print(f"Error: Failed to start systemd unit for task {task['id']}")
                    q.complete(task['id'], success=False)

        time.sleep(1) # Poll interval

    print("Worker shutdown complete.")

# --- CLI Interface ---
def main():
    """A simple command-line interface for the orchestrator."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <worker|add|stats>")
        print("  worker                  - Start a worker process.")
        print("  add <name> <cmd> [pri]  - Add a new task.")
        print("  stats                   - Show queue statistics.")
        sys.exit(1)

    q = TaskQueue()
    command = sys.argv[1]

    if command == "worker":
        executor = SystemdExecutor()
        worker_loop(q, executor)
    elif command == "add":
        if len(sys.argv) < 4:
            print("Usage: add <name> <command> [priority]")
            sys.exit(1)
        name = sys.argv[2]
        cmd = sys.argv[3]
        priority = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        task_id = q.add(name, cmd, priority)
        if task_id:
            print(f"Successfully added task '{name}' with ID {task_id}.")
    elif command == "stats":
        print(json.dumps(q.stats(), indent=2))
    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()