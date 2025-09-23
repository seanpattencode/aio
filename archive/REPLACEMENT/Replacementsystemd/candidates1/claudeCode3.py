#!/usr/bin/env python3
"""
claudeCode3: Production-Ready Orchestrator (<200 lines)
Synthesizes: Android reaping + Chrome WAL + Firefox journal patterns
Best for: Production deployments, high reliability
"""
import sqlite3
import subprocess
import signal
import logging
import json
import sys
import os
import time
from pathlib import Path
from typing import Dict, Optional, List
from enum import Enum

# Production configuration
DB_PATH = Path("/var/lib/aios/orchestrator.db")
UNIT_PREFIX = "aios-"
WATCHDOG_INTERVAL = 30

class WorkflowState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ProductionOrchestrator:
    """Production-grade systemd orchestrator with reliability patterns"""

    def __init__(self):
        self.running = True
        self.children = {}

        # Setup logging to systemd journal
        try:
            from systemd import journal
            handler = journal.JournalHandler(SYSLOG_IDENTIFIER='aios')
            logging.root.addHandler(handler)
        except ImportError:
            pass

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Initialize database with production settings
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(DB_PATH), isolation_level=None)
        self._init_db()

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGCHLD, self._reap_children)

    def _init_db(self):
        """Initialize SQLite with production optimizations"""
        # Chrome/Firefox WAL mode patterns
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA cache_size=-8000;
            PRAGMA busy_timeout=5000;
            PRAGMA wal_autocheckpoint=1000;

            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                command TEXT NOT NULL,
                state TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                retry_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                started_at DATETIME,
                completed_at DATETIME,
                pid INTEGER,
                exit_code INTEGER,
                unit_name TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_state_priority
            ON workflows(state, priority DESC, created_at);
        """)

    def _handle_signal(self, signum, frame):
        """Graceful shutdown handler"""
        self.logger.info(f"Received signal {signum}, shutting down")
        self.running = False
        try:
            from systemd import daemon
            daemon.notify("STOPPING=1")
        except ImportError:
            pass

    def _reap_children(self, signum, frame):
        """Android-style zombie reaping pattern"""
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break

                exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1

                # Update database
                self.db.execute("""
                    UPDATE workflows
                    SET state = ?, exit_code = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE pid = ?
                """, ('completed' if exit_code == 0 else 'failed', exit_code, pid))

                self.logger.info(f"Reaped child {pid} with exit code {exit_code}")

            except ChildProcessError:
                break

    def submit(self, name: str, command: str, priority: int = 0) -> int:
        """Submit new workflow"""
        cursor = self.db.execute("""
            INSERT INTO workflows (name, command, priority)
            VALUES (?, ?, ?)
        """, (name, command, priority))

        workflow_id = cursor.lastrowid
        self.logger.info(f"Submitted workflow {workflow_id}: {name}")
        return workflow_id

    def deploy_workflow(self, workflow_id: int) -> bool:
        """Deploy workflow as systemd service with production settings"""
        row = self.db.execute("""
            SELECT name, command, priority FROM workflows WHERE id = ?
        """, (workflow_id,)).fetchone()

        if not row:
            return False

        name, command, priority = row
        unit_name = f"{UNIT_PREFIX}{workflow_id}.service"

        # Create transient unit with production properties
        properties = [
            "--collect",  # Clean up automatically
            "--property=Type=exec",
            "--property=Restart=on-failure",
            "--property=RestartSec=10",
            f"--property=Nice={-priority}",  # Higher priority = lower nice
            "--property=StandardOutput=journal",
            "--property=StandardError=journal",
            "--property=KillMode=control-group",  # Kill all children
            "--property=TimeoutStopSec=30",
            # Resource limits
            "--property=MemoryMax=4G",
            "--property=CPUQuota=200%",  # 2 cores max
            "--property=TasksMax=1000",
            # Security
            "--property=PrivateTmp=yes",
            "--property=ProtectSystem=strict",
            "--property=NoNewPrivileges=yes",
        ]

        # Use systemd-run for transient units
        result = subprocess.run(
            ["systemd-run", "--user", "--unit", unit_name] + properties +
            ["--", "sh", "-c", command],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            # Get PID from systemd
            pid_result = subprocess.run(
                ["systemctl", "--user", "show", unit_name, "--property=MainPID"],
                capture_output=True, text=True
            )

            pid = 0
            if pid_result.returncode == 0 and "=" in pid_result.stdout:
                pid = int(pid_result.stdout.split("=")[1].strip())

            # Update database
            self.db.execute("""
                UPDATE workflows
                SET state = 'running', started_at = CURRENT_TIMESTAMP,
                    pid = ?, unit_name = ?
                WHERE id = ?
            """, (pid, unit_name, workflow_id))

            self.logger.info(f"Deployed workflow {workflow_id} as {unit_name} (PID: {pid})")
            return True

        return False

    def monitor(self):
        """Monitor and process workflows"""
        # Deploy pending workflows
        pending = self.db.execute("""
            SELECT id FROM workflows
            WHERE state = 'pending'
            ORDER BY priority DESC, created_at
            LIMIT 5
        """).fetchall()

        for row in pending:
            self.deploy_workflow(row[0])

        # Check running workflows
        running = self.db.execute("""
            SELECT id, unit_name, retry_count, max_retries
            FROM workflows WHERE state = 'running'
        """).fetchall()

        for workflow_id, unit_name, retry_count, max_retries in running:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", unit_name],
                capture_output=True, text=True
            )

            if result.stdout.strip() == "inactive":
                # Check if should retry
                if retry_count < max_retries:
                    self.db.execute("""
                        UPDATE workflows
                        SET state = 'pending', retry_count = retry_count + 1
                        WHERE id = ?
                    """, (workflow_id,))
                    self.logger.info(f"Retrying workflow {workflow_id} (attempt {retry_count + 1})")

        # Periodic WAL checkpoint (Firefox pattern)
        self.db.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def run(self):
        """Main service loop"""
        try:
            from systemd import daemon
            daemon.notify("READY=1")
        except ImportError:
            pass

        self.logger.info("Production orchestrator started")

        while self.running:
            try:
                self.monitor()

                # Update systemd watchdog
                try:
                    from systemd import daemon
                    daemon.notify("WATCHDOG=1")
                except ImportError:
                    pass

                time.sleep(5)

            except Exception as e:
                self.logger.error(f"Monitor error: {e}")
                time.sleep(10)

        self.logger.info("Orchestrator shutdown complete")

def main():
    """CLI interface"""
    if len(sys.argv) < 2:
        print("Usage: claudeCode3.py <submit|status|run>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "submit" and len(sys.argv) >= 4:
        orch = ProductionOrchestrator()
        workflow_id = orch.submit(sys.argv[2], sys.argv[3])
        print(f"Workflow ID: {workflow_id}")

    elif cmd == "status":
        db = sqlite3.connect(str(DB_PATH))
        for row in db.execute("SELECT id, name, state FROM workflows"):
            print(f"{row[0]}: {row[1]} [{row[2]}]")

    elif cmd == "run":
        orch = ProductionOrchestrator()
        orch.run()

if __name__ == "__main__":
    main()