#!/usr/bin/env python3
"""
Systemd-based orchestrator - Ultra-minimal, ultra-fast
Leverages systemd for process management, restart, and zombie reaping
"""
import os
import sys
import time
import subprocess
import json
import sqlite3
import uuid
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_queue.db"
UNIT_PREFIX = "aios-"

# ==============================================================================
# Synthesized SQLite Task Queue
# ==============================================================================

class SQLiteTaskQueue:
    """A robust, process-safe, file-based task queue using SQLite."""

    def __init__(self, path):
        self.path = path
        self._create_table()

    def _get_conn(self):
        """Creates a new connection with optimal settings."""
        conn = sqlite3.connect(self.path, timeout=10)
        # WAL mode allows concurrent readers and one writer.
        conn.execute("PRAGMA journal_mode = WAL;")
        # Tolerate busy signals for up to 5 seconds.
        conn.execute("PRAGMA busy_timeout = 5000;")
        # Use a dictionary-like row factory for easier data access.
        conn.row_factory = sqlite3.Row
        return conn

    def _create_table(self):
        """Creates the queue table if it doesn't exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aios_tasks (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('ready', 'running', 'done', 'failed')),
                    priority INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error_log TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    locked_by TEXT,
                    locked_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_status
                ON aios_tasks (status, priority, created_at);
            """)

    def add_task(self, payload: dict, priority: int = 0) -> str:
        """Adds a new task to the queue."""
        task_id = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO aios_tasks (id, payload, status, priority) VALUES (?, ?, 'ready', ?)",
                (task_id, json.dumps(payload), priority)
            )
        print(f"Added task {task_id}")
        return task_id

    def claim_task(self, worker_id: str) -> (dict | None):
        """Atomically claims the highest-priority task."""
        conn = self._get_conn()
        try:
            # An IMMEDIATE transaction locks the database for writing, preventing
            # other workers from trying to claim a job simultaneously.
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM aios_tasks
                WHERE status = 'ready'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            """)
            row = cursor.fetchone()

            if not row:
                conn.commit()
                return None

            task_id = row['id']
            cursor.execute("""
                UPDATE aios_tasks
                SET status = 'running',
                    locked_by = ?,
                    locked_at = CURRENT_TIMESTAMP,
                    attempts = attempts + 1
                WHERE id = ?
                RETURNING *
            """, (worker_id, task_id))
            task = cursor.fetchone()
            conn.commit()
            return dict(task) if task else None
        except sqlite3.Error:
            conn.rollback()
            raise

    def complete_task(self, task_id: str):
        """Marks a task as successfully completed."""
        with self._get_conn() as conn:
            conn.execute("UPDATE aios_tasks SET status = 'done' WHERE id = ?", (task_id,))

    def fail_task(self, task_id: str, error: str):
        """Marks a task as failed and logs the error."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE aios_tasks SET status = 'failed', error_log = ? WHERE id = ?",
                (error, task_id)
            )

# ==============================================================================
# AIOS Worker Logic
# ==============================================================================

def run_worker():
    """Main loop for a worker process."""
    worker_id = f"worker-{os.getpid()}"
    print(f"Starting AIOS worker: {worker_id}")
    queue = SQLiteTaskQueue(DB_PATH)
    
    while True:
        task = queue.claim_task(worker_id)
        if task:
            try:
                print(f"[{worker_id}] Processing task {task['id']}: {task['payload']}")
                # --- AI WORKFLOW EXECUTION WOULD GO HERE ---
                # Example: Execute a command from the payload
                payload = json.loads(task['payload'])
                command = payload.get("command")
                if command:
                    # In a real system, you'd use subprocess.run with better error handling
                    print(f"[{worker_id}] Executing: {command}")
                    time.sleep(5) # Simulate a long-running AI task
                    print(f"[{worker_id}] Finished command: {command}")
                
                # --- END OF WORKFLOW EXECUTION ---
                queue.complete_task(task['id'])
                print(f"[{worker_id}] Completed task {task['id']}")
            except Exception:
                error = traceback.format_exc()
                print(f"[{worker_id}] Failed task {task['id']}: {error}")
                queue.fail_task(task['id'], error)
        else:
            # If no tasks, wait before polling again to avoid busy-looping
            time.sleep(2)

# ==============================================================================
# Original Systemd Orchestrator (Unchanged)
# ==============================================================================

class SystemdOrchestrator:
    """Minimal systemd wrapper - let systemd handle everything"""
    def __init__(self):
        self.jobs = {}
        self._load_jobs()

    def _run(self, *args):
        return subprocess.run(["systemctl", "--user"] + list(args),
                            capture_output=True, text=True, check=False)

    def _load_jobs(self):
        result = self._run("list-units", f"{UNIT_PREFIX}*.service", "--no-legend", "--plain")
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if parts:
                    name = parts[0].replace('.service', '').replace(UNIT_PREFIX, '')
                    self.jobs[name] = parts[0]

    def add_job(self, name: str, command: str, restart: str = "always") -> str:
        unit_name = f"{UNIT_PREFIX}{name}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_content = f"""[Unit]
Description=AIOS Job: {name}

[Service]
Type=simple
ExecStart={command}
Restart={restart}
RestartSec=1

[Install]
WantedBy=default.target
"""
        unit_path.write_text(unit_content)
        self.jobs[name] = unit_name
        self._run("daemon-reload")
        return unit_name

    def start_job(self, name: str):
        if name not in self.jobs: return
        self._run("start", self.jobs[name])

    def stop_job(self, name: str):
        if name not in self.jobs: return
        self._run("stop", self.jobs[name])
    
    def status(self) -> dict:
        status = {}
        for name, unit in self.jobs.items():
            result = self._run("show", unit, "--property=ActiveState,MainPID")
            props = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    props[k] = v
            status[name] = {
                'state': props.get('ActiveState', 'unknown'),
                'pid': int(props.get('MainPID', 0))
            }
        return status

    def cleanup(self):
        print("Stopping and removing all AIOS systemd units...")
        for unit in self.jobs.values():
            self._run("stop", unit)
            self._run("disable", unit)
            unit_path = Path(f"~/.config/systemd/user/{unit}").expanduser()
            if unit_path.exists():
                unit_path.unlink()
        self._run("daemon-reload")
        if DB_PATH.exists():
            print(f"Removing database file at {DB_PATH}")
            DB_PATH.unlink()

# ==============================================================================
# Main Entry Point & CLI
# ==============================================================================

def main():
    """Main entry with integrated task queue management"""
    orch = SystemdOrchestrator()
    queue = SQLiteTaskQueue(DB_PATH)

    # The main job is now a worker that polls the queue.
    # We can run multiple workers for parallel processing.
    if "worker-1" not in orch.jobs:
        worker_cmd = f"/usr/bin/python3 {__file__} worker"
        orch.add_job("worker-1", worker_cmd)
        orch.add_job("worker-2", worker_cmd) # Add a second worker

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "worker":
            run_worker()
        elif cmd == "start":
            for name in orch.jobs:
                orch.start_job(name)
                print(f"Started {name}")
        elif cmd == "stop":
            for name in orch.jobs:
                orch.stop_job(name)
                print(f"Stopped {name}")
        elif cmd == "status":
            print(json.dumps(orch.status(), indent=2))
        elif cmd == "add-task":
            # Example: python3 your_script.py add-task '{"command": "echo hello world"}'
            if len(sys.argv) > 2:
                try:
                    payload_str = sys.argv[2]
                    payload = json.loads(payload_str)
                    queue.add_task(payload)
                except json.JSONDecodeError:
                    print("Error: Task payload must be valid JSON.", file=sys.stderr)
                except Exception as e:
                    print(f"An error occurred: {e}", file=sys.stderr)
            else:
                print("Usage: add-task '<json_payload>'")
        elif cmd == "cleanup":
            orch.cleanup()
            print("Cleaned up all units and database.")
        else:
            print(f"Usage: {sys.argv[0]} [start|stop|status|add-task|cleanup|worker]")
    else:
        status = orch.status()
        print("=== Systemd Orchestrator Status ===")
        print(f"Database Path: {DB_PATH}")
        print(f"Managed Jobs: {len(status)}")
        for name, info in status.items():
            print(f"  - {name}: {info['state']} (PID: {info['pid']})")
        print("\nUse 'start' to run workers, 'add-task' to queue jobs, and 'status' to check.")


if __name__ == "__main__":
    main()