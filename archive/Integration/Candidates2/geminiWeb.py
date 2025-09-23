#!/usr/bin/env python3
"""
AIOS Orchestrator: A unified job orchestrator and scheduler.

This script combines a high-performance SQLite task queue with robust systemd-based
process execution. It manages the entire lifecycle of tasks, including dependencies,
retries, scheduling, and resource management, by delegating process control to
systemd's transient unit capabilities.
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
DB_PATH = Path.home() / ".aios_orchestrator.db"
UNIT_PREFIX = "aios-"

# --- Systemd Command Helpers ---
# Use user scope if not root for broader compatibility without sudo.
USE_USER_SCOPE = os.geteuid() != 0
SYSTEMCTL = ["systemctl", "--user"] if USE_USER_SCOPE else ["systemctl"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"] if USE_USER_SCOPE else ["systemd-run", "--collect", "--quiet"]

# --- High-Performance SQLite Settings ---
PRAGMAS = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-8000;
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;
PRAGMA wal_autocheckpoint=1000;
"""

class Orchestrator:
    """Manages the task lifecycle, from database state to systemd execution."""

    def __init__(self, db_path=DB_PATH):
        """Initializes the database connection and schema."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(PRAGMAS + """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                cmd TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                priority INT DEFAULT 0,
                retries INT DEFAULT 0,
                unit_name TEXT,
                props TEXT,   -- JSON for systemd properties (rtprio, mem_mb, etc.)
                deps TEXT,    -- JSON array of dependency IDs
                created_at INT,
                started_at INT,
                completed_at INT
            );
            CREATE INDEX IF NOT EXISTS idx_status_prio ON tasks(status, priority DESC, created_at);
        """)

    def _sh(self, cmd: List[str]) -> subprocess.CompletedProcess:
        """Helper for running shell commands."""
        return subprocess.run(cmd, text=True, capture_output=True, check=False)

    def add(self, name: str, cmd: str, **kwargs) -> Optional[int]:
        """Adds a task to the database."""
        props = {k: v for k, v in kwargs.items() if v is not None and k in
                 {'rtprio', 'mem_mb', 'cpu_w', 'schedule', 'nice', 'slice', 'cwd'}}
        try:
            cursor = self.conn.execute(
                "INSERT INTO tasks (name, cmd, priority, deps, props, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, cmd, kwargs.get("prio", 0), json.dumps(kwargs.get("deps") or []),
                 json.dumps(props), int(time.time() * 1000))
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            print(f"Error: Task name '{name}' already exists.", file=sys.stderr)
            return None

    def _get_runnable_tasks(self) -> List[sqlite3.Row]:
        """Finds pending tasks whose dependencies are met."""
        return self.conn.execute("""
            SELECT * FROM tasks
            WHERE status='pending' AND (deps IS NULL OR deps = '[]' OR NOT EXISTS (
                SELECT 1 FROM json_each(tasks.deps) AS d
                JOIN tasks AS dt ON dt.id = d.value
                WHERE dt.status != 'completed'
            )) ORDER BY priority DESC, created_at ASC
        """).fetchall()

    def _finalize_task(self, task_id: int, success: bool):
        """Marks a task as complete or requeues it for retry."""
        task = self.conn.execute("SELECT retries FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task: return

        if success:
            self.conn.execute("UPDATE tasks SET status='completed', completed_at=? WHERE id=?", (int(time.time() * 1000), task_id))
        elif task['retries'] < 3:
            delay_ms = 1000 * (2 ** task['retries'])
            new_at = int(time.time() * 1000) + delay_ms
            self.conn.execute("UPDATE tasks SET status='pending', retries=retries+1, at=? WHERE id=?", (new_at, task_id))
        else:
            self.conn.execute("UPDATE tasks SET status='failed', completed_at=? WHERE id=?", (int(time.time() * 1000), task_id))

    def _launch_task_via_systemd(self, task: sqlite3.Row):
        """Constructs and executes a systemd-run command for a given task."""
        unit_name = f"{UNIT_PREFIX}{task['name']}-{task['id']}.service"
        props = json.loads(task['props'] or '{}')
        cmd = [*SYSDRUN, "--unit", unit_name]
        
        # Apply properties
        prop_map = {
            "rtprio": ("CPUSchedulingPolicy=rr", f"CPUSchedulingPriority={props.get('rtprio')}"),
            "mem_mb": (f"MemoryMax={props.get('mem_mb')}M",),
            "cpu_w": (f"CPUWeight={props.get('cpu_w')}",),
            "nice": (f"Nice={props.get('nice')}",),
            "slice": (f"--slice={props.get('slice')}",), # Slice is a direct argument
            "cwd": (f"WorkingDirectory={props.get('cwd')}",)
        }
        for key, values in prop_map.items():
            if props.get(key) is not None:
                if key == 'slice':
                    cmd.append(values)
                else:
                    for value in values:
                        cmd.append(f"--property={value}")

        cmd.extend(["--property=StandardOutput=journal", "--property=StandardError=journal"])
        if props.get('schedule'):
            cmd.append(f"--on-calendar={props['schedule']}")
        
        cmd.extend(["--", "/bin/sh", "-c", task['cmd']])
        
        result = self._sh(cmd)
        if result.returncode == 0:
            status = 'scheduled' if props.get('schedule') else 'running'
            self.conn.execute("UPDATE tasks SET status=?, unit_name=?, started_at=? WHERE id=?",
                              (status, unit_name, int(time.time() * 1000), task['id']))
        else:
            print(f"Error launching systemd unit for task {task['id']}: {result.stderr.strip()}", file=sys.stderr)
            self._finalize_task(task['id'], success=False)

    def reconcile(self, running_tasks: Dict[int, str]):
        """Checks the status of systemd units and updates the database."""
        if not running_tasks: return
        
        res = self._sh([*SYSTEMCTL, "show", *running_tasks.values(), "--property=ActiveState,Result"])
        status_blocks = res.stdout.strip().split('\n\n')
        
        for i, (task_id, unit_name) in enumerate(running_tasks.items()):
            props = dict(line.split("=", 1) for line in status_blocks[i].splitlines() if "=" in line)
            if props.get("ActiveState") in ("inactive", "failed"):
                success = props.get("Result") == "success"
                print(f"Task {task_id} ('{unit_name}') finished. Success: {success}")
                self._finalize_task(task_id, success)

    def run_worker(self, max_concurrent: int = os.cpu_count()):
        """Main worker loop to manage the task lifecycle."""
        print(f"Worker started (PID: {os.getpid()}). Max concurrent jobs: {max_concurrent}")
        shutdown = threading.Event()
        signal.signal(signal.SIGINT, lambda s, f: shutdown.set())
        signal.signal(signal.SIGTERM, lambda s, f: shutdown.set())

        while not shutdown.is_set():
            with self.conn:
                running_tasks = {r['id']: r['unit_name'] for r in
                                 self.conn.execute("SELECT id, unit_name FROM tasks WHERE status='running' AND unit_name IS NOT NULL")}
            
            # 1. Reconcile current state
            self.reconcile(running_tasks)
            
            # 2. Launch new tasks if there's capacity
            num_to_launch = max_concurrent - len(running_tasks)
            if num_to_launch > 0:
                for task in self._get_runnable_tasks()[:num_to_launch]:
                    self._launch_task_via_systemd(dict(task))
            
            time.sleep(2) # Poll interval
        print("\nWorker shutdown complete.")

def main():
    """Defines and handles the command-line interface."""
    parser = argparse.ArgumentParser(description="AIOS Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_p = subparsers.add_parser("add", help="Add a new task.")
    add_p.add_argument("name", help="Unique name for the task.")
    add_p.add_argument("command", help="The shell command to execute.")
    add_p.add_argument("--prio", type=int, default=0, help="Priority (higher is sooner).")
    add_p.add_argument("--deps", type=json.loads, help="JSON list of task IDs, e.g., '[1,2]'.")
    add_p.add_argument("--schedule", help="systemd OnCalendar string for scheduling.")
    add_p.add_argument("--rtprio", type=int, help="Real-time priority (1-99).")
    add_p.add_argument("--mem_mb", type=int, help="Memory limit in MB.")
    add_p.add_argument("--cpu_w", type=int, help="CPU weight (1-10000).")

    worker_p = subparsers.add_parser("worker", help="Run a worker process.")
    worker_p.add_argument("concurrency", type=int, nargs="?", default=os.cpu_count(), help="Max concurrent jobs.")

    subparsers.add_parser("stats", help="Show queue statistics.")
    subparsers.add_parser("install", help="Generate a systemd unit file for the worker.")

    args = parser.parse_args()
    orch = Orchestrator()

    if args.command == "worker":
        orch.run_worker(max_concurrent=args.concurrency)
    elif args.command == "add":
        task_id = orch.add(args.name, args.command, prio=args.prio, deps=args.deps,
                           schedule=args.schedule, rtprio=args.rtprio,
                           mem_mb=args.mem_mb, cpu_w=args.cpu_w)
        if task_id:
            print(f"Task '{args.name}' added with ID {task_id}.")
    elif args.command == "stats":
        print(json.dumps(orch.get_stats(), indent=2))
    elif args.command == "install":
        print(generate_systemd_unit())

if __name__ == "__main__":
    main()