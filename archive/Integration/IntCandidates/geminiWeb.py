#!/usr/bin/env python3
"""
AIOS Orchestrator: Synthesized Production Model

- Uses a high-performance SQLite queue for task state.
- Delegates execution and reaping to systemd via transient units.
- Combines the best patterns from claudeCodeD and aios_systemd_orchestrator.py.
"""
import argparse
import json
import os
import shlex
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- Configuration ---
DB_PATH = Path.home() / ".aios/orchestrator.db"
UNIT_PREFIX = "aios-task-"

# PRAGMAS from claudeCodeD for high-performance WAL mode
PRAGMAS = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-8000;
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;
PRAGMA wal_autocheckpoint=1000;
"""


class Orchestrator:
    """Manages task state in SQLite and orchestrates execution via systemd."""

    def __init__(self, db_path=DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Initializes the database schema."""
        self.conn.executescript(PRAGMAS + """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                cmd TEXT NOT NULL,
                prio INT DEFAULT 0,
                status TEXT DEFAULT 'pending', -- pending, running, completed, failed
                at INT, -- scheduled_at (ms)
                retries INT DEFAULT 0,
                props TEXT, -- JSON blob for systemd properties (rt, mem, etc.)
                deps TEXT,  -- JSON array of dependency IDs
                unit_name TEXT,
                created_at INT,
                started_at INT,
                completed_at INT,
                result TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_status_prio ON tasks(status, prio DESC, at);
        """)

    def _sh(self, cmd: List[str]) -> subprocess.CompletedProcess:
        """Helper for running shell commands."""
        return subprocess.run(cmd, text=True, capture_output=True, check=False)

    def add(self, name: str, cmd: str, **kwargs) -> Optional[int]:
        """Adds a task to the queue."""
        props = {
            "rtprio": kwargs.get("rtprio"),
            "mem_mb": kwargs.get("mem_mb"),
            "cpu_w": kwargs.get("cpu_w")
        }
        try:
            cursor = self.conn.execute(
                """INSERT INTO tasks (name, cmd, prio, at, deps, props, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    cmd,
                    kwargs.get("prio", 0),
                    kwargs.get("at", int(time.time() * 1000)),
                    json.dumps(kwargs.get("deps") or []),
                    json.dumps({k: v for k, v in props.items() if v is not None}),
                    int(time.time() * 1000)
                )
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            print(f"Error: Task name '{name}' already exists.", file=sys.stderr)
            return None

    def _get_next(self) -> Optional[sqlite3.Row]:
        """Atomically get the next runnable task."""
        now = int(time.time() * 1000)
        try:
            # Atomically find, update, and return the next task
            cursor = self.conn.execute("""
                UPDATE tasks SET status='running', started_at=? WHERE id = (
                    SELECT id FROM tasks
                    WHERE status='pending' AND at <= ?
                    AND (deps IS NULL OR deps = '[]' OR NOT EXISTS (
                        SELECT 1 FROM json_each(tasks.deps) AS d
                        JOIN tasks AS dt ON dt.id = d.value
                        WHERE dt.status != 'completed'
                    ))
                    ORDER BY prio DESC, at ASC LIMIT 1
                ) RETURNING *
            """, (now, now))
            return cursor.fetchone()
        except sqlite3.OperationalError:  # Fallback for older SQLite versions
            with self.conn:
                row = self.conn.execute(
                    "SELECT id FROM tasks WHERE status='pending' AND at <= ? ORDER BY prio DESC, at ASC LIMIT 1",
                    (now,)
                ).fetchone()
                if not row: return None
                self.conn.execute("UPDATE tasks SET status='running', started_at=? WHERE id=?", (now, row['id']))
                return self.conn.execute("SELECT * FROM tasks WHERE id=?", (row['id'],)).fetchone()

    def _finalize_task(self, task_id: int, success: bool):
        """Mark a task done or requeue for retry."""
        task = self.conn.execute("SELECT retries FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task: return

        if success:
            self.conn.execute(
                "UPDATE tasks SET status='completed', completed_at=? WHERE id=?",
                (int(time.time() * 1000), task_id)
            )
        else:  # Retry logic
            retries = task['retries']
            if retries < 3:
                delay_ms = 1000 * (2 ** retries)
                self.conn.execute(
                    "UPDATE tasks SET status='pending', retries=retries+1, at=? WHERE id=?",
                    (int(time.time() * 1000) + delay_ms, task_id)
                )
            else:
                self.conn.execute(
                    "UPDATE tasks SET status='failed', completed_at=? WHERE id=?",
                    (int(time.time() * 1000), task_id)
                )

    def _run_with_systemd(self, task: sqlite3.Row) -> Optional[str]:
        """Launch a task using systemd-run."""
        unit_name = f"{UNIT_PREFIX}{task['name']}-{task['id']}.service"
        props = json.loads(task['props'] or '{}')
        
        cmd = ["systemd-run", "--user", "--collect", "--quiet", "--unit", unit_name]
        
        # Add properties
        if props.get("rtprio"):
            cmd += [f"--property=CPUSchedulingPolicy=rr", f"--property=CPUSchedulingPriority={props['rtprio']}"]
        if props.get("mem_mb"):
            cmd += [f"--property=MemoryMax={props['mem_mb']}M"]
        if props.get("cpu_w"):
            cmd += [f"--property=CPUWeight={props['cpu_w']}"]
        
        cmd.extend(["--property=StandardOutput=journal", "--property=StandardError=journal",
                    "--", "/bin/sh", "-c", task['cmd']])

        result = self._sh(cmd)
        if result.returncode == 0:
            self.conn.execute("UPDATE tasks SET unit_name=? WHERE id=?", (unit_name, task['id']))
            return unit_name
        else:
            print(f"Error launching systemd unit for task {task['id']}: {result.stderr}", file=sys.stderr)
            self._finalize_task(task['id'], success=False)
            return None

    def run_worker(self, max_concurrent: int = os.cpu_count()):
        """Main worker loop to manage the task queue and systemd units."""
        print(f"Worker started (PID: {os.getpid()}). Max concurrent jobs: {max_concurrent}")
        running_tasks: Dict[int, str] = {}  # {task_id: unit_name}
        shutdown = threading.Event()

        def _handle_signal(*_):
            print("\nShutdown signal received. Finishing running tasks...")
            shutdown.set()
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        while not shutdown.is_set():
            # 1. Monitor running tasks
            for task_id, unit_name in list(running_tasks.items()):
                res = self._sh(["systemctl", "--user", "show", unit_name, "--property=ActiveState,Result"])
                status = {k: v for k, v in (line.split("=", 1) for line in res.stdout.splitlines() if "=" in line)}
                
                if status.get("ActiveState") in ("inactive", "failed"):
                    success = status.get("Result") == "success"
                    print(f"Task {task_id} ('{unit_name}') finished. Success: {success}")
                    self._finalize_task(task_id, success)
                    del running_tasks[task_id]

            # 2. Launch new tasks if capacity allows
            while len(running_tasks) < max_concurrent:
                if shutdown.is_set(): break
                task = self._get_next()
                if not task:
                    break  # No more pending tasks
                
                print(f"Launching task {task['id']}: {task['name']}")
                unit_name = self._run_with_systemd(task)
                if unit_name:
                    running_tasks[task['id']] = unit_name
                else:  # Failed to launch
                    break  # Avoid rapid-fire launch failures
            
            time.sleep(1)  # Poll interval
        print("Worker shutdown complete.")

    def get_stats(self) -> Dict[str, int]:
        """Returns a count of tasks by status."""
        return {r['status']: r['count'] for r in self.conn.execute(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        )}

def generate_systemd_unit() -> str:
    """Generate a systemd service file for the worker daemon."""
    return f"""[Unit]
Description=AIOS Orchestrator Worker
After=network.target

[Service]
Type=simple
ExecStart={sys.executable} {os.path.abspath(__file__)} worker
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""

def main():
    """Defines and handles the command-line interface."""
    parser = argparse.ArgumentParser(description="AIOS Systemd Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Worker command
    worker_parser = subparsers.add_parser("worker", help="Run a worker process.")
    worker_parser.add_argument("concurrency", type=int, nargs="?", default=os.cpu_count(),
                               help="Max number of concurrent jobs.")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new task.")
    add_parser.add_argument("name", help="Unique name for the task.")
    add_parser.add_argument("command", help="The shell command to execute.")
    add_parser.add_argument("--prio", type=int, default=0, help="Task priority (higher is sooner).")
    add_parser.add_argument("--delay_ms", type=int, default=0, help="Delay execution by milliseconds.")
    add_parser.add_argument("--deps", type=json.loads, help="JSON list of task IDs it depends on, e.g., '[1, 2]'.")
    add_parser.add_argument("--rtprio", type=int, help="Real-time priority (1-99).")
    add_parser.add_argument("--mem_mb", type=int, help="Memory limit in MB.")
    add_parser.add_argument("--cpu_w", type=int, help="CPU weight (1-10000).")

    # Stats and Install commands
    subparsers.add_parser("stats", help="Show queue statistics.")
    subparsers.add_parser("install", help="Generate a systemd unit file for the worker.")

    args = parser.parse_args()
    orch = Orchestrator()

    if args.command == "worker":
        orch.run_worker(max_concurrent=args.concurrency)
    elif args.command == "add":
        at = int(time.time() * 1000) + args.delay_ms
        task_id = orch.add(args.name, args.command, prio=args.prio, at=at, deps=args.deps,
                           rtprio=args.rtprio, mem_mb=args.mem_mb, cpu_w=args.cpu_w)
        if task_id:
            print(f"Task '{args.name}' added with ID {task_id}.")
    elif args.command == "stats":
        print(json.dumps(orch.get_stats(), indent=2))
    elif args.command == "install":
        print(generate_systemd_unit())

if __name__ == "__main__":
    main()