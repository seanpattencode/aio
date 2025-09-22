#!/usr/bin/env python3
"""

AIOS Task Queue with SQLite - Optimized for systemd-based orchestrator

Combines reliability of SQLite with systemd process management
"""

import os
import sys
import time
import sqlite3
import threading
import subprocess
import json
import logging
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("aios_task_queue")

BASE_DIR = Path(__file__).parent.absolute()
UNIT_PREFIX = "aios-"

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Task:
    id: int
    name: str
    command: str
    status: TaskStatus
    priority: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[str]
    error: Optional[str]
    metadata: Optional[Dict]
    retries: int = 0
    max_retries: int = 3

class AIOSTaskQueue:
    """SQLite-based task queue optimized for AIOS workflow management"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(BASE_DIR / "aios.db")
        self.lock = threading.RLock()
        self._init_db()
        
    @contextmanager
    def _get_connection(self):
        """Get a thread-safe database connection with proper settings"""
        with self.lock:
            conn = sqlite3.connect(self.db_path, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
            conn.execute("PRAGMA busy_timeout=5000")  # Handle concurrent access gracefully
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def _init_db(self):
        """Initialize the database schema"""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    started_at DATETIME,
                    completed_at DATETIME,
                    result TEXT,
                    error TEXT,
                    metadata TEXT,
                    retries INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    systemd_unit TEXT
                )
            """)
            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status_priority ON tasks(status, priority DESC)")
            # conn.execute("CREATE INDEX IF NOT EXISTS idx_retry ON tasks(status, retries, created_at)")
            # conn.execute("CREATE INDEX IF NOT EXISTS idx_systemd_unit ON tasks(systemd_unit)")
            conn.commit()

    def add_task(self, name: str, command: str, priority: int = 0, 
                 metadata: Optional[Dict] = None, max_retries: int = 3) -> int:
        """Add a new task to the queue"""
        with self._get_connection() as conn:
            meta_json = json.dumps(metadata) if metadata else None
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (name, command, priority, metadata, max_retries)
                VALUES (?, ?, ?, ?, ?)
            """, (name, command, priority, meta_json, max_retries))
            conn.commit()
            return cursor.lastrowid

    def get_next_task(self) -> Optional[Task]:
        """Get the next available task and mark it as running"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Use immediate transaction to lock the database
            cursor.execute("BEGIN IMMEDIATE")
            
            try:
                # Find next task that's pending or failed with retries remaining
                cursor.execute("""
                    SELECT * FROM tasks 
                    WHERE (status = 'pending' OR 
                          (status = 'failed' AND retries < max_retries))
                    ORDER BY priority DESC, created_at ASC 
                    LIMIT 1
                """)
                task_row = cursor.fetchone()
                
                if task_row:
                    task_id = task_row['id']
                    current_retries = task_row['retries']
                    new_retries = current_retries + 1 if task_row['status'] == 'failed' else 0
                    
                    # Update task status to running
                    cursor.execute("""
                        UPDATE tasks 
                        SET status = 'running', started_at = CURRENT_TIMESTAMP, retries = ?
                        WHERE id = ?
                    """, (new_retries, task_id))
                    
                    conn.commit()
                    return self._row_to_task(task_row)
                    
                conn.commit()
                return None
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Error getting next task: {e}")
                return None

    def update_task(self, task_id: int, status: TaskStatus, 
                   result: Optional[str] = None, error: Optional[str] = None):
        """Update task status and results"""
        with self._get_connection() as conn:
            if status == TaskStatus.COMPLETED:
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP, result = ?, error = ?
                    WHERE id = ?
                """, (status.value, result, error, task_id))
            else:
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?, result = ?, error = ?
                    WHERE id = ?
                """, (status.value, result, error, task_id))
            conn.commit()

    def link_task_to_systemd(self, task_id: int, unit_name: str):
        """Link a task to a systemd unit for tracking"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE tasks 
                SET systemd_unit = ?
                WHERE id = ?
            """, (unit_name, task_id))
            conn.commit()

    def get_task_by_systemd_unit(self, unit_name: str) -> Optional[Task]:
        """Get task by associated systemd unit name"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE systemd_unit = ?", (unit_name,))
            row = cursor.fetchone()
            return self._row_to_task(row) if row else None

    def get_tasks(self, status: Optional[TaskStatus] = None, 
                 limit: int = 100, offset: int = 0) -> List[Task]:
        """Get tasks with optional status filter"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT * FROM tasks 
                    WHERE status = ? 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (status.value, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM tasks 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            stats = {}
            
            for status in TaskStatus:
                cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", (status.value,))
                stats[status.value] = cursor.fetchone()[0]
                
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'failed' AND retries >= max_retries")
            stats['permanently_failed'] = cursor.fetchone()[0]
            
            return stats

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task object"""
        return Task(
            id=row['id'],
            name=row['name'],
            command=row['command'],
            status=TaskStatus(row['status']),
            priority=row['priority'],
            created_at=datetime.fromisoformat(row['created_at']),
            started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
            result=row['result'],
            error=row['error'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            retries=row['retries'],
            max_retries=row['max_retries']
        )

    def cleanup_old_tasks(self, days: int = 7):
        """Clean up completed tasks older than specified days"""
        with self._get_connection() as conn:
            conn.execute("""
                DELETE FROM tasks 
                WHERE completed_at IS NOT NULL 
                AND completed_at < datetime('now', ?)
            """, (f'-{days} days',))
            conn.commit()

class SystemdOrchestrator:
    """Extended systemd wrapper with task queue integration"""

    def __init__(self, task_queue: AIOSTaskQueue):
        self.task_queue = task_queue
        self.jobs = {}
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
        """Create systemd service unit and add to task queue"""
        unit_name = f"{UNIT_PREFIX}{name}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)

        # Add to task queue first
        task_id = self.task_queue.add_task(
            name=name,
            command=command,
            metadata={"systemd_unit": unit_name}
        )

        # Create systemd unit
        unit_content = f"""[Unit]
Description=AIOS Job: {name}

[Service]
Type=simple
ExecStart=/bin/sh -c '{command}'
Restart={restart}
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
        
        # Link task to systemd unit
        self.task_queue.link_task_to_systemd(task_id, unit_name)
        
        self._run("daemon-reload")
        return unit_name

    def start_job(self, name: str) -> Tuple[float, Optional[int]]:
        """Start job via systemd and update task status"""
        if name not in self.jobs:
            return -1, None
        
        # Get the associated task
        task = self.task_queue.get_task_by_systemd_unit(self.jobs[name])
        if task:
            self.task_queue.update_task(task.id, TaskStatus.RUNNING)
        
        start = time.perf_counter()
        result = self._run("start", self.jobs[name])
        elapsed = (time.perf_counter() - start) * 1000
        
        if result.returncode != 0 and task:
            self.task_queue.update_task(task.id, TaskStatus.FAILED, error=result.stderr)
        
        return elapsed, task.id if task else None

    def stop_job(self, name: str) -> float:
        """Stop job immediately"""
        if name not in self.jobs:
            return -1
        
        # Get the associated task
        task = self.task_queue.get_task_by_systemd_unit(self.jobs[name])
        if task:
            self.task_queue.update_task(task.id, TaskStatus.CANCELLED)
        
        start = time.perf_counter()
        self._run("stop", self.jobs[name])
        return (time.perf_counter() - start) * 1000

    # Other methods remain similar but would be enhanced with task queue integration

def main():
    """Main entry with task queue integration"""
    task_queue = AIOSTaskQueue()
    orch = SystemdOrchestrator(task_queue)

    # Handle commands
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "add_task":
            if len(sys.argv) >= 4:
                name = sys.argv[2]
                command = sys.argv[3]
                priority = int(sys.argv[4]) if len(sys.argv) > 4 else 0
                task_id = task_queue.add_task(name, command, priority)
                print(f"Added task {task_id}: {name}")
            else:
                print("Usage: add_task <name> <command> [priority]")
        
        elif cmd == "queue_stats":
            stats = task_queue.get_stats()
            print(json.dumps(stats, indent=2))
        
        elif cmd == "list_tasks":
            status = TaskStatus(sys.argv[2]) if len(sys.argv) > 2 else None
            tasks = task_queue.get_tasks(status=status)
            for task in tasks:
                print(f"{task.id}: {task.name} ({task.status})")
        
        # Existing commands
        elif cmd == "start":
            for name in orch.jobs:
                ms, task_id = orch.start_job(name)
                print(f"Started {name} in {ms:.2f}ms (task: {task_id})")
        
        # Other existing commands...
        else:
            print(f"Usage: {sys.argv[0]} [add_task|queue_stats|list_tasks|start|stop|restart|status|cleanup]")
    else:
        # Show status with queue info
        status = orch.status()
        stats = task_queue.get_stats()
        
        print(f"=== Systemd Orchestrator ===")
        print(f"Jobs: {len(status)}")
        print(f"Tasks: {json.dumps(stats, indent=2)}")
        
        for name, info in status.items():
            print(f"  {name}: {info['state']} (PID: {info['pid']})")

if __name__ == "__main__":
    main()