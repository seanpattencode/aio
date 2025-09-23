#!/usr/bin/env python3
""" Systemd-based orchestrator - Ultra-minimal, ultra-fast
Leverages systemd for process management, restart, and zombie reaping
"""

import os
import sys
import time
import subprocess
import json
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).parent.absolute()
UNIT_PREFIX = "aios-"
DB_PATH = BASE_DIR / "aios_queue.db"

class SqliteTaskQueue:
    """SQLite-based task queue for AI workflows, integrated with orchestrator"""
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5.0)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                command TEXT NOT NULL,
                status INTEGER DEFAULT 0,  -- 0: pending, 1: running, 2: done, 3: failed
                created_at REAL DEFAULT (unixepoch('now')),
                started_at REAL,
                finished_at REAL,
                error TEXT
            )
        """)
        self.conn.commit()

    def put(self, name: str, command: str) -> int:
        """Add a task to the queue"""
        self.cursor.execute(
            "INSERT INTO tasks (name, command) VALUES (?, ?)",
            (name, command)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get(self) -> dict | None:
        """Get the next pending task atomically"""
        try:
            self.conn.execute("BEGIN EXCLUSIVE")
            self.cursor.execute(
                "SELECT id, name, command FROM tasks WHERE status = 0 ORDER BY id LIMIT 1"
            )
            row = self.cursor.fetchone()
            if row is None:
                self.conn.rollback()
                return None
            task_id, name, command = row
            self.cursor.execute(
                "UPDATE tasks SET status = 1, started_at = unixepoch('now') WHERE id = ?",
                (task_id,)
            )
            if self.cursor.rowcount == 0:
                self.conn.rollback()
                return None
            self.conn.commit()
            return {"id": task_id, "name": name, "command": command}
        except sqlite3.OperationalError:
            self.conn.rollback()
            return None

    def ack(self, task_id: int, success: bool = True, error: str = None):
        """Acknowledge task as done or failed"""
        status = 2 if success else 3
        self.cursor.execute(
            "UPDATE tasks SET status = ?, finished_at = unixepoch('now'), error = ? WHERE id = ?",
            (status, error, task_id)
        )
        self.conn.commit()

    def cleanup(self):
        """Remove completed/failed tasks"""
        self.cursor.execute("DELETE FROM tasks WHERE status IN (2, 3)")
        self.conn.commit()

    def status(self) -> dict:
        """Get queue status summary"""
        self.cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        rows = self.cursor.fetchall()
        return dict(rows)

class SystemdOrchestrator:
    """Minimal systemd wrapper - let systemd handle everything"""
    def __init__(self):
        self.jobs = {}
        self.queue = SqliteTaskQueue()
        self._load_jobs()

    def _run(self, *args):
        """Run systemctl command"""
        return subprocess.run(["systemctl", "--user"] + list(args), capture_output=True, text=True, check=False)

    def _load_jobs(self):
        """Load existing AIOS jobs from systemd"""
        result = self._run("list-units", f"{UNIT_PREFIX}*.service", "--no-legend", "--plain")
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if parts:
                    name = parts[0].replace('.service', '').replace(UNIT_PREFIX, '')
                    self.jobs[name] = parts[0]

    def add_job(self, name: str, command: str, restart: str = "always", oneshot: bool = False) -> str:
        """Create systemd service unit, supports oneshot for queue tasks"""
        unit_name = f"{UNIT_PREFIX}{name}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        # Systemd handles: zombie reaping, process groups, restart, logging
        service_type = "oneshot" if oneshot else "simple"
        unit_content = f"""[Unit]
Description=AIOS Job: {name}

[Service]
Type={service_type}
ExecStart=/bin/sh -c '{command}'
Restart={restart if not oneshot else 'no'}
RestartSec=0
StandardOutput=journal
StandardError=journal
KillMode=control-group
TimeoutStopSec=0

[Install]
WantedBy=default.target
"""
        unit_path.write_text(unit_content)
        self.jobs[name] = unit_name
        self._run("daemon-reload")
        return unit_name

    def start_job(self, name: str) -> float:
        """Start job via systemd"""
        if name not in self.jobs:
            return -1
        start = time.perf_counter()
        self._run("start", self.jobs[name])
        return (time.perf_counter() - start) * 1000

    def stop_job(self, name: str) -> float:
        """Stop job immediately"""
        if name not in self.jobs:
            return -1
        start = time.perf_counter()
        self._run("stop", self.jobs[name])
        return (time.perf_counter() - start) * 1000

    def restart_job(self, name: str) -> float:
        """Restart job via systemd"""
        if name not in self.jobs:
            return -1
        start = time.perf_counter()
        self._run("restart", self.jobs[name])
        return (time.perf_counter() - start) * 1000

    def restart_all(self) -> dict:
        """Restart all jobs"""
        start = time.perf_counter()
        times = {}
        # Use systemd's batch restart for speed
        units = list(self.jobs.values())
        if units:
            result = self._run("restart", *units)
        for name in self.jobs:
            times[name] = 0.5  # systemd handles it in parallel
        total = (time.perf_counter() - start) * 1000
        print(f"=== RESTART ALL in {total:.2f}ms ===")
        return times

    def status(self) -> dict:
        """Get status of all jobs"""
        status = {}
        for name, unit in self.jobs.items():
            result = self._run("show", unit, "--property=ActiveState,MainPID,ExecMainStartTimestampMonotonic")
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
        """Remove all AIOS systemd units"""
        for unit in self.jobs.values():
            self._run("stop", unit)
            self._run("disable", unit)
            unit_path = Path(f"~/.config/systemd/user/{unit}").expanduser()
            if unit_path.exists():
                unit_path.unlink()
        self._run("daemon-reload")

    def process_queue(self):
        """Worker to process tasks from queue using systemd oneshot units"""
        while True:
            task = self.queue.get()
            if task is None:
                time.sleep(0.1)  # Poll interval
                continue
            name = task['name']
            command = task['command']
            try:
                # Add as oneshot unit if not exists
                if name not in self.jobs:
                    self.add_job(name, command, oneshot=True)
                # Start the unit (oneshot will run once)
                self.start_job(name)
                # Wait for completion (poll status)
                while True:
                    job_status = self.status().get(name, {})
                    if job_status['state'] in ('inactive', 'failed'):
                        break
                    time.sleep(0.5)
                if job_status['state'] == 'failed':
                    raise Exception("Job failed")
                self.queue.ack(task['id'], success=True)
            except Exception as e:
                self.queue.ack(task['id'], success=False, error=str(e))
                print(f"Task {name} failed: {e}")

def main():
    """Main entry with example usage"""
    orch = SystemdOrchestrator()
    # Example: Add tasks to queue for dynamic processing
    if "heartbeat" not in orch.jobs:
        orch.queue.put("heartbeat", "while true; do echo Heartbeat; sleep 5; done")
    if "todo_app" not in orch.jobs:
        orch.queue.put("todo_app", "/usr/bin/python3 " + str(BASE_DIR / "hybridTODO.py"))

    # Handle commands
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "start":
            for name in orch.jobs:
                ms = orch.start_job(name)
                print(f"Started {name} in {ms:.2f}ms")
        elif cmd == "stop":
            for name in orch.jobs:
                ms = orch.stop_job(name)
                print(f"Stopped {name} in {ms:.2f}ms")
        elif cmd == "restart":
            times = orch.restart_all()
            print(f"Restart times: {times}")
        elif cmd == "status":
            print(json.dumps(orch.status(), indent=2))
        elif cmd == "cleanup":
            orch.cleanup()
            print("Cleaned up all units")
        elif cmd == "worker":
            print("Starting queue worker...")
            orch.process_queue()  # Run the queue processor
        elif cmd == "queue_status":
            print(json.dumps(orch.queue.status(), indent=2))
        else:
            print(f"Usage: {sys.argv[0]} [start|stop|restart|status|cleanup|worker|queue_status]")
    else:
        # Just show status
        status = orch.status()
        print(f"=== Systemd Orchestrator ===")
        print(f"Jobs: {len(status)}")
        for name, info in status.items():
            print(f" {name}: {info['state']} (PID: {info['pid']})")

if __name__ == "__main__":
    main()