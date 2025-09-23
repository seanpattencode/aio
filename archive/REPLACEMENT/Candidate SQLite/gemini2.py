#!/usr/bin/env python3
"""
AIOS Orchestrator - Systemd + SQLite Task Queue
Leverages systemd for process management and SQLite for persistent, reliable task queuing.
"""
import os
import sys
import time
import subprocess
import json
import sqlite3
import threading
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_tasks.db"
UNIT_PREFIX = "aios-"

# --- SQLite Task Queue ---
class TaskQueue:
    """A robust, persistent task queue using SQLite, inspired by large-scale applications."""

    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = self._create_connection()
        self._init_db()

    def _create_connection(self):
        """Create a new database connection with optimized settings."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        # From Chrome/Firefox: WAL mode is essential for concurrent reads and writes.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        """Initialize the database schema."""
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    run_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    retry_count INTEGER DEFAULT 0
                )
            ''')
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_run_at ON tasks (status, run_at);")

    def enqueue(self, name: str, command: str, delay_seconds: int = 0) -> int:
        """Add a new task to the queue."""
        now = time.time()
        run_at = now + delay_seconds
        with self.conn:
            cursor = self.conn.execute(
                "INSERT OR IGNORE INTO tasks (name, command, created_at, run_at) VALUES (?, ?, ?, ?)",
                (name, command, now, run_at)
            )
            return cursor.lastrowid

    def dequeue(self) -> dict:
        """Atomically dequeue the next available task."""
        now = time.time()
        with self.conn:
            # This transaction ensures that only one worker can select and update a task at a time.
            # This is the most critical part of any database-backed queue.
            cursor = self.conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' AND run_at <= ? ORDER BY id ASC LIMIT 1",
                (now,)
            )
            task = cursor.fetchone()
            if task:
                self.conn.execute(
                    "UPDATE tasks SET status = 'running', started_at = ? WHERE id = ?",
                    (now, task['id'])
                )
                return dict(task)
        return None

    def mark_done(self, task_id: int):
        """Mark a task as successfully completed."""
        with self.conn:
            self.conn.execute("UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?", (time.time(), task_id))

    def mark_failed(self, task_id: int):
        """Mark a task as failed and schedule it for a future retry."""
        with self.conn:
            cursor = self.conn.execute("SELECT retry_count FROM tasks WHERE id = ?", (task_id,))
            task = cursor.fetchone()
            if task:
                retries = task['retry_count'] + 1
                # Exponential backoff for retries: 10s, 40s, 90s, etc.
                delay = 10 * (retries ** 2)
                self.conn.execute(
                    "UPDATE tasks SET status = 'pending', retry_count = ?, run_at = ? WHERE id = ?",
                    (retries, time.time() + delay, task_id)
                )

    def get_task_by_name(self, name: str):
        """Retrieve a task by its unique name."""
        with self.conn:
            cursor = self.conn.execute("SELECT * FROM tasks WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

# --- Systemd Orchestrator ---
class SystemdOrchestrator:
    """Minimal systemd wrapper to run processes reliably."""
    def _run(self, *args):
        return subprocess.run(["systemctl", "--user"] + list(args),
                              capture_output=True, text=True, check=False)

    def add_and_start_job(self, name: str, command: str) -> bool:
        """Create and immediately start a systemd service unit."""
        unit_name = f"{UNIT_PREFIX}{name}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_content = f"""[Unit]
Description=AIOS Task: {name}
[Service]
Type=simple
ExecStart=/bin/sh -c '{command}'
StandardOutput=journal
StandardError=journal
KillMode=control-group
[Install]
WantedBy=default.target
"""
        unit_path.write_text(unit_content)
        self._run("daemon-reload")
        result = self._run("start", unit_name)
        return result.returncode == 0

    def stop_and_remove_job(self, name: str):
        """Stop and delete the systemd unit."""
        unit_name = f"{UNIT_PREFIX}{name}.service"
        self._run("stop", unit_name)
        self._run("disable", unit_name)
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        if unit_path.exists():
            unit_path.unlink()
        self._run("daemon-reload")

    def is_active(self, name: str) -> bool:
        """Check if a systemd service is active."""
        unit_name = f"{UNIT_PREFIX}{name}.service"
        result = self._run("is-active", unit_name)
        return result.stdout.strip() == "active"

# --- Main Application ---
def main_worker_loop():
    """The core logic that connects the queue to the orchestrator."""
    task_queue = TaskQueue(DB_PATH)
    orchestrator = SystemdOrchestrator()
    print("AIOS Worker started. Waiting for tasks...")

    # On startup, ensure systemd is clean for any tasks marked as 'running' in the DB
    # This handles recovery from a crash.
    with task_queue.conn:
        cursor = task_queue.conn.execute("SELECT * FROM tasks WHERE status = 'running'")
        for task in cursor.fetchall():
            print(f"Recovering task '{task['name']}' from previous run.")
            orchestrator.stop_and_remove_job(task['name'])
            task_queue.mark_failed(task['id']) # Mark as failed to force a retry

    active_tasks = {}  # {task_id: task_dict}

    try:
        while True:
            # 1. Dequeue a new task if we have capacity
            if not active_tasks: # Simple worker, runs one task at a time
                task = task_queue.dequeue()
                if task:
                    print(f"Dequeued task '{task['name']}' (ID: {task['id']}). Starting via systemd.")
                    success = orchestrator.add_and_start_job(task['name'], task['command'])
                    if success:
                        active_tasks[task['id']] = task
                    else:
                        print(f"Failed to start task '{task['name']}' in systemd.")
                        task_queue.mark_failed(task['id'])

            # 2. Monitor active tasks
            completed_task_ids = []
            for task_id, task in active_tasks.items():
                if not orchestrator.is_active(task['name']):
                    print(f"Task '{task['name']}' (ID: {task_id}) has completed.")
                    completed_task_ids.append(task_id)
                    # Note: We assume success here. For more robustness, you could
                    # check `systemctl status` for the exit code.
                    task_queue.mark_done(task_id)
                    orchestrator.stop_and_remove_job(task['name'])

            for task_id in completed_task_ids:
                del active_tasks[task_id]

            time.sleep(1) # Polling interval
    except KeyboardInterrupt:
        print("\nShutdown signal received. Cleaning up...")
        for task_id, task in active_tasks.items():
            orchestrator.stop_and_remove_job(task['name'])
            task_queue.mark_failed(task_id) # Ensure it reruns on next start

def cli_handler():
    """Handle command-line interface commands."""
    if len(sys.argv) < 2:
        print("Usage: ./aios.py [worker|add|status] [args...]")
        sys.exit(1)

    command = sys.argv[1]
    task_queue = TaskQueue(DB_PATH)

    if command == "worker":
        main_worker_loop()
    elif command == "add":
        if len(sys.argv) != 4:
            print("Usage: ./aios.py add <name> \"<command>\"")
            sys.exit(1)
        name, cmd_str = sys.argv[2], sys.argv[3]
        task_id = task_queue.enqueue(name, cmd_str)
        if task_id:
            print(f"Successfully enqueued task '{name}' with ID {task_id}.")
        else:
            print(f"Task with name '{name}' already exists.")
    elif command == "status":
        name = sys.argv[2] if len(sys.argv) > 2 else None
        if name:
            task = task_queue.get_task_by_name(name)
            print(json.dumps(task, indent=2) if task else f"No task found with name '{name}'")
        else:
            print("Listing all tasks...")
            with task_queue.conn:
                for row in task_queue.conn.execute("SELECT * FROM tasks ORDER BY id"):
                    print(dict(row))
    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    cli_handler()