#!/usr/bin/env python3
"""
ClaudeCode1: Basic SQLite Task Management with Systemd Integration
Simple, robust task queue with atomic operations and WAL mode for speed
"""

import os
import sys
import time
import sqlite3
import json
import subprocess
import threading
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_tasks.db"
UNIT_PREFIX = "aios-"

class TaskStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class SimpleTaskQueue:
    """Minimal SQLite task queue with best practices from production systems"""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """Connection with WAL mode and optimal pragmas"""
        conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Create minimal schema with single efficient index"""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'ready',
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    started_at INTEGER,
                    completed_at INTEGER,
                    result TEXT,
                    retries INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ready ON tasks(status, priority DESC, created_at)
                WHERE status = 'ready'
            """)
            conn.commit()

    def push(self, name: str, command: str, priority: int = 0) -> int:
        """Add task to queue"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (name, command, priority) VALUES (?, ?, ?)",
                (name, command, priority)
            )
            conn.commit()
            return cursor.lastrowid

    def pop(self) -> Optional[Dict[str, Any]]:
        """Atomically get and mark next task as running"""
        with self.lock:
            with self._get_conn() as conn:
                # Single atomic operation using UPDATE with RETURNING
                cursor = conn.execute("""
                    UPDATE tasks
                    SET status = 'running', started_at = strftime('%s', 'now')
                    WHERE id = (
                        SELECT id FROM tasks
                        WHERE status = 'ready'
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                    )
                    RETURNING id, name, command
                """)

                row = cursor.fetchone()
                conn.commit()

                if row:
                    return dict(row)
                return None

    def complete(self, task_id: int, success: bool, result: str = None):
        """Mark task as completed or failed"""
        status = 'completed' if success else 'failed'
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE tasks
                SET status = ?, completed_at = strftime('%s', 'now'), result = ?
                WHERE id = ?
            """, (status, result, task_id))

            # Auto-retry failed tasks up to 3 times
            if not success:
                conn.execute("""
                    UPDATE tasks
                    SET status = 'ready', retries = retries + 1
                    WHERE id = ? AND retries < 3
                """, (task_id,))

            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(CASE WHEN status='ready' THEN 1 END) as ready,
                    COUNT(CASE WHEN status='running' THEN 1 END) as running,
                    COUNT(CASE WHEN status='completed' THEN 1 END) as completed,
                    COUNT(CASE WHEN status='failed' THEN 1 END) as failed
                FROM tasks
            """)
            return dict(cursor.fetchone())

class SystemdOrchestrator:
    """Minimal systemd wrapper"""

    def __init__(self):
        self.jobs = {}
        self.task_queue = SimpleTaskQueue()
        self._load_jobs()

    def _run(self, *args):
        """Run systemctl command"""
        return subprocess.run(["systemctl", "--user"] + list(args),
                            capture_output=True, text=True, check=False)

    def _load_jobs(self):
        """Load existing AIOS jobs from systemd"""
        result = self._run("list-units", f"{UNIT_PREFIX}*.service", "--no-legend", "--plain")
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if parts:
                    name = parts[0].replace('.service', '').replace(UNIT_PREFIX, '')
                    self.jobs[name] = parts[0]

    def add_job(self, name: str, command: str, restart: str = "always") -> str:
        """Create systemd service unit"""
        unit_name = f"{UNIT_PREFIX}{name}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)

        unit_content = f"""[Unit]
Description=AIOS Job: {name}

[Service]
Type=simple
ExecStart=/bin/sh -c '{command}'
Restart={restart}
RestartSec=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""
        unit_path.write_text(unit_content)
        self.jobs[name] = unit_name
        self._run("daemon-reload")
        return unit_name

    def add_task(self, name: str, command: str, priority: int = 0) -> int:
        """Add one-shot task to queue"""
        return self.task_queue.push(name, command, priority)

    def run_worker(self):
        """Worker loop that processes tasks from queue"""
        print("Task worker started")
        while True:
            task = self.task_queue.pop()
            if task:
                print(f"Running task {task['id']}: {task['name']}")
                try:
                    result = subprocess.run(
                        task['command'],
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    success = result.returncode == 0
                    output = f"{result.stdout}\n{result.stderr}".strip()
                    self.task_queue.complete(task['id'], success, output[:1000])
                    print(f"Task {task['id']} {'completed' if success else 'failed'}")
                except Exception as e:
                    self.task_queue.complete(task['id'], False, str(e))
                    print(f"Task {task['id']} error: {e}")
            else:
                time.sleep(0.5)

    def start_job(self, name: str):
        """Start job via systemd"""
        if name in self.jobs:
            self._run("start", self.jobs[name])

    def stop_job(self, name: str):
        """Stop job via systemd"""
        if name in self.jobs:
            self._run("stop", self.jobs[name])

    def status(self) -> dict:
        """Get status of all jobs and tasks"""
        status = {}

        # Systemd jobs
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

        # Task queue stats
        status['_queue'] = self.task_queue.get_stats()
        return status

def main():
    """Main entry point"""
    orch = SystemdOrchestrator()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "worker":
            orch.run_worker()

        elif cmd == "add-task":
            if len(sys.argv) < 4:
                print("Usage: add-task <name> <command> [priority]")
                sys.exit(1)
            priority = int(sys.argv[4]) if len(sys.argv) > 4 else 0
            task_id = orch.add_task(sys.argv[2], sys.argv[3], priority)
            print(f"Added task {task_id}")

        elif cmd == "add-job":
            if len(sys.argv) < 4:
                print("Usage: add-job <name> <command>")
                sys.exit(1)
            orch.add_job(sys.argv[2], sys.argv[3])
            print(f"Added job {sys.argv[2]}")

        elif cmd == "start":
            if len(sys.argv) > 2:
                orch.start_job(sys.argv[2])
                print(f"Started {sys.argv[2]}")
            else:
                for name in orch.jobs:
                    orch.start_job(name)
                    print(f"Started {name}")

        elif cmd == "stop":
            if len(sys.argv) > 2:
                orch.stop_job(sys.argv[2])
                print(f"Stopped {sys.argv[2]}")
            else:
                for name in orch.jobs:
                    orch.stop_job(name)
                    print(f"Stopped {name}")

        elif cmd == "status":
            status = orch.status()
            print(json.dumps(status, indent=2))

        else:
            print(f"Usage: {sys.argv[0]} [worker|add-task|add-job|start|stop|status]")
    else:
        # Show status
        status = orch.status()
        print(f"=== Systemd + SQLite Orchestrator ===")
        print(f"Jobs: {len([k for k in status.keys() if not k.startswith('_')])}")
        print(f"Queue: {status.get('_queue', {})}")
        for name, info in status.items():
            if not name.startswith('_'):
                print(f"  {name}: {info['state']} (PID: {info['pid']})")

if __name__ == "__main__":
    main()