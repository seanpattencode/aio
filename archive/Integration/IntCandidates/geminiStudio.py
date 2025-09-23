#!/usr/bin/env python3
"""
job_orchestrator.py: A unified job orchestration and scheduling system.
Integrates direct process management with optional systemd execution for robustness.
"""
import argparse
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

# --- Database Setup and Management ---

def get_db_connection(db_path: str = "orchestrator.db") -> sqlite3.Connection:
    """Establishes and configures the SQLite database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Optimizations from claudeCodeD
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA cache_size=-8000;
        PRAGMA temp_store=MEMORY;
        PRAGMA busy_timeout=5000;
    """)
    return conn

def initialize_schema(conn: sqlite3.Connection):
    """Initializes the database schema."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            command TEXT NOT NULL,
            args TEXT DEFAULT '[]',
            status TEXT DEFAULT 'queued',
            priority INTEGER DEFAULT 0,
            scheduled_at INTEGER,
            worker_id TEXT,
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            result TEXT,
            created_at INTEGER NOT NULL,
            started_at INTEGER,
            ended_at INTEGER,
            use_systemd BOOLEAN DEFAULT FALSE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_status_priority ON jobs(status, priority DESC, scheduled_at)")

# --- Core Orchestrator Class ---

class JobOrchestrator:
    """Manages job lifecycle, from creation to execution and completion."""

    def __init__(self, db_path: str = "orchestrator.db"):
        self.conn = get_db_connection(db_path)
        initialize_schema(self.conn)

    def add_job(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        priority: int = 0,
        delay_ms: int = 0,
        use_systemd: bool = False,
    ) -> int:
        """Adds a new job to the database."""
        current_time = int(time.time() * 1000)
        scheduled_at = current_time + delay_ms if delay_ms > 0 else current_time
        args_json = json.dumps(args or [])

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO jobs (name, command, args, priority, scheduled_at, use_systemd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, command, args_json, priority, scheduled_at, use_systemd, current_time),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_jobs(self):
        """Lists all jobs in the database."""
        cursor = self.conn.execute("SELECT id, name, command, status, use_systemd FROM jobs ORDER BY created_at DESC")
        return cursor.fetchall()

    def get_next_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Atomically retrieves and locks the next available job."""
        now = int(time.time() * 1000)
        cursor = self.conn.cursor()

        # Find a suitable job
        cursor.execute(
            """
            SELECT id FROM jobs
            WHERE status = 'queued' AND scheduled_at <= ?
            ORDER BY priority DESC, scheduled_at
            LIMIT 1
            """,
            (now,),
        )
        job_row = cursor.fetchone()
        if not job_row:
            return None

        job_id = job_row['id']

        # Atomically claim it
        cursor.execute(
            """
            UPDATE jobs
            SET status = 'running', worker_id = ?, started_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (worker_id, now, job_id),
        )
        self.conn.commit()

        if cursor.rowcount > 0:
            job = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(job)
        return None

    def finalize_job(
        self,
        job_id: int,
        success: bool,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Marks a job as done or failed."""
        status = 'done' if success else 'failed'
        ended_at = int(time.time() * 1000)
        self.conn.execute(
            "UPDATE jobs SET status = ?, result = ?, error_message = ?, ended_at = ?, worker_id = NULL WHERE id = ?",
            (status, result, error, ended_at, job_id),
        )
        self.conn.commit()

# --- Worker and Execution Logic ---

class Worker:
    """A worker that executes jobs."""

    def __init__(self, orchestrator: JobOrchestrator, worker_id: str):
        self.orchestrator = orchestrator
        self.worker_id = worker_id

    def run_once(self):
        """Fetches and runs a single job."""
        job = self.orchestrator.get_next_job(self.worker_id)
        if not job:
            print("No available jobs.")
            return

        print(f"Executing job {job['name']} (ID: {job['id']})...")
        command = [job['command']] + json.loads(job['args'])

        try:
            if job['use_systemd']:
                self._run_with_systemd(job, command)
            else:
                self._run_with_subprocess(job, command)
        except Exception as e:
            self.orchestrator.finalize_job(job['id'], success=False, error=str(e))
            print(f"An unexpected error occurred while running job {job['name']}: {e}")

    def _run_with_systemd(self, job: Dict[str, Any], command: List[str]):
        """Executes a job using systemd-run."""
        unit_name = f"orchestrator-{job['name']}.service"
        systemd_command = [
            "systemd-run",
            "--user",
            "--collect",
            "--quiet",
            f"--unit={unit_name}",
            "--property=StandardOutput=journal",
            "--property=StandardError=journal",
        ] + command

        result = subprocess.run(systemd_command, capture_output=True, text=True)

        if result.returncode == 0:
            self.orchestrator.finalize_job(job['id'], success=True, result=f"Systemd unit '{unit_name}' started.")
        else:
            self.orchestrator.finalize_job(job['id'], success=False, error=result.stderr)

    def _run_with_subprocess(self, job: Dict[str, Any], command: List[str]):
        """Executes a job using a direct subprocess call."""
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,  # 5-minute timeout
                check=True,
            )
            output = {
                "stdout": process.stdout[:1000],
                "stderr": process.stderr[:1000],
            }
            self.orchestrator.finalize_job(job['id'], success=True, result=json.dumps(output))
        except subprocess.CalledProcessError as e:
            error_output = {
                "stdout": e.stdout[:1000],
                "stderr": e.stderr[:1000],
                "returncode": e.returncode,
            }
            self.orchestrator.finalize_job(job['id'], success=False, error=json.dumps(error_output))
        except subprocess.TimeoutExpired:
            self.orchestrator.finalize_job(job['id'], success=False, error="Job timed out after 300 seconds.")

# --- Command-Line Interface ---

def main():
    """Main function to handle command-line arguments."""
    parser = argparse.ArgumentParser(description="A unified job orchestrator.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 'add' command
    add_parser = subparsers.add_parser("add", help="Add a new job.")
    add_parser.add_argument("name", help="A unique name for the job.")
    add_parser.add_argument("cmd", help="The command to execute.")
    add_parser.add_argument("args", nargs="*", help="Arguments for the command.")
    add_parser.add_argument("--priority", type=int, default=0, help="Job priority (higher is sooner).")
    add_parser.add_argument("--delay", type=int, default=0, help="Delay execution by N milliseconds.")
    add_parser.add_argument("--systemd", action="store_true", help="Execute the job via systemd-run.")

    # 'list' command
    subparsers.add_parser("list", help="List all jobs.")

    # 'worker' command
    worker_parser = subparsers.add_parser("worker", help="Run a worker to execute a single job.")
    worker_parser.add_argument("--id", default=f"worker-{os.getpid()}", help="A unique ID for the worker.")

    args = parser.parse_args()
    orchestrator = JobOrchestrator()

    if args.command == "add":
        try:
            job_id = orchestrator.add_job(
                name=args.name,
                command=args.cmd,
                args=args.args,
                priority=args.priority,
                delay_ms=args.delay,
                use_systemd=args.systemd,
            )
            print(f"Job '{args.name}' added with ID: {job_id}")
        except sqlite3.IntegrityError:
            print(f"Error: A job with the name '{args.name}' already exists.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        jobs = orchestrator.list_jobs()
        if not jobs:
            print("No jobs found.")
            return

        print(f"{'ID':<5} {'Name':<20} {'Status':<10} {'Systemd':<8} {'Command'}")
        print("-" * 70)
        for job in jobs:
            print(f"{job['id']:<5} {job['name']:<20} {job['status']:<10} {'Yes' if job['use_systemd'] else 'No':<8} {job['command']}")

    elif args.command == "worker":
        worker = Worker(orchestrator, args.id)
        worker.run_once()

if __name__ == "__main__":
    main()