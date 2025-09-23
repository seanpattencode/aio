#!/usr/bin/env python3
"""
ClaudeCodeA: Hybrid SQLite Task Orchestrator
Combines claude1's blazing speed with claudeCode2's enterprise features
Optimized for both simple high-throughput and complex workflow scenarios
"""

import os
import sys
import time
import json
import sqlite3
import subprocess
import threading
import signal
import hashlib
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple, Union
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime

# Configuration
BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_hybrid.db"
UNIT_PREFIX = "aios-"

class TaskMode(Enum):
    """Operating modes for different use cases"""
    FAST = "fast"       # Minimal overhead, maximum speed (claude1 mode)
    ADVANCED = "advanced"  # Full features with dependencies (claudeCode2 mode)

class TaskStatus(Enum):
    """Task states"""
    PENDING = "pending"
    LEASED = "leased"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Task:
    """Task representation"""
    id: int
    name: str
    command: str
    mode: TaskMode
    payload: Optional[Dict[str, Any]] = None
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    scheduled_at: Optional[int] = None
    lease_until: Optional[int] = None
    worker_id: Optional[str] = None
    attempts: int = 0
    max_retries: int = 3
    parent_ids: Optional[List[int]] = None
    unique_key: Optional[str] = None

class HybridTaskQueue:
    """
    Hybrid queue supporting both ultra-fast simple mode and advanced scheduling
    Best of both worlds: claude1's speed + claudeCode2's features
    """

    def __init__(self, db_path: str = str(DB_PATH), mode: TaskMode = TaskMode.FAST):
        self.db_path = db_path
        self.mode = mode
        self.lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """Get connection with mode-optimized settings"""
        if self.mode == TaskMode.FAST:
            # Fast mode: single persistent connection
            if not hasattr(self, '_conn'):
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._optimize_fast()
            yield self._conn
        else:
            # Advanced mode: connection per operation
            conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            self._optimize_advanced(conn)
            try:
                yield conn
            finally:
                conn.close()

    def _optimize_fast(self):
        """Apply claude1's proven optimizations for speed"""
        self._conn.executescript("""
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;
            PRAGMA temp_store = MEMORY;
            PRAGMA mmap_size = 30000000000;
            PRAGMA cache_size = -64000;
            PRAGMA page_size = 4096;
            PRAGMA busy_timeout = 5000;
        """)

    def _optimize_advanced(self, conn):
        """Apply claudeCode2's settings for reliability"""
        conn.executescript("""
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;
            PRAGMA foreign_keys = ON;
            PRAGMA temp_store = MEMORY;
            PRAGMA mmap_size = 30000000000;
            PRAGMA cache_size = -64000;
        """)

    def _init_db(self):
        """Initialize hybrid schema supporting both modes"""
        with self._get_conn() as conn:
            conn.executescript("""
                -- Main tasks table (optimized for both modes)
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    mode TEXT DEFAULT 'fast',
                    payload BLOB,  -- BLOB for speed (claude1)
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    unique_key TEXT,
                    scheduled_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                    lease_until INTEGER,
                    worker_id TEXT,
                    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                    started_at INTEGER,
                    completed_at INTEGER,
                    attempts INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    backoff_ms INTEGER DEFAULT 1000,
                    result BLOB,
                    error TEXT
                );

                -- Fast mode index (claude1 pattern)
                CREATE INDEX IF NOT EXISTS idx_fast ON tasks(status, priority DESC, scheduled_at)
                    WHERE status = 'pending' AND mode = 'fast';

                -- Advanced mode indexes (claudeCode2 pattern)
                CREATE INDEX IF NOT EXISTS idx_advanced ON tasks(status, priority DESC, scheduled_at, id)
                    WHERE status = 'pending' AND mode = 'advanced';

                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique
                    ON tasks(unique_key)
                    WHERE unique_key IS NOT NULL AND status IN ('pending', 'leased', 'running');

                CREATE INDEX IF NOT EXISTS idx_lease
                    ON tasks(lease_until)
                    WHERE status = 'leased';

                -- Dependencies table for advanced mode
                CREATE TABLE IF NOT EXISTS task_deps (
                    child_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    parent_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    PRIMARY KEY (child_id, parent_id)
                );

                -- Run history for advanced mode
                CREATE TABLE IF NOT EXISTS task_runs (
                    id INTEGER PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    worker_id TEXT NOT NULL,
                    started_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                    ended_at INTEGER,
                    exit_code INTEGER,
                    output TEXT
                );
            """)
            conn.commit()

    # FAST MODE OPERATIONS (claude1 patterns)

    def push_fast(self, name: str, command: str, priority: int = 0,
                  payload: Any = None) -> int:
        """Ultra-fast task push using atomic operations"""
        payload_blob = json.dumps(payload).encode() if payload else None
        scheduled = int(time.time() * 1000)

        with self.lock:
            with self._get_conn() as conn:
                cursor = conn.execute("""
                    INSERT INTO tasks (name, command, mode, payload, priority, scheduled_at)
                    VALUES (?, ?, 'fast', ?, ?, ?)
                """, (name, command, payload_blob, priority, scheduled))
                conn.commit()
                return cursor.lastrowid

    def pop_fast(self) -> Optional[Dict[str, Any]]:
        """Atomic pop with UPDATE-RETURNING (fastest pattern)"""
        with self.lock:
            with self._get_conn() as conn:
                now = int(time.time() * 1000)
                cursor = conn.execute("""
                    UPDATE tasks
                    SET status = 'running', started_at = ?
                    WHERE id = (
                        SELECT id FROM tasks
                        WHERE status = 'pending'
                            AND mode = 'fast'
                            AND scheduled_at <= ?
                        ORDER BY priority DESC, scheduled_at ASC
                        LIMIT 1
                    )
                    RETURNING id, name, command, payload
                """, (now, now))

                row = cursor.fetchone()
                conn.commit()

                if row:
                    return {
                        'id': row['id'],
                        'name': row['name'],
                        'command': row['command'],
                        'payload': json.loads(row['payload']) if row['payload'] else None
                    }
                return None

    # ADVANCED MODE OPERATIONS (claudeCode2 patterns)

    def push_advanced(self, name: str, command: str, priority: int = 0,
                     delay_ms: int = 0, unique_key: str = None,
                     parent_ids: List[int] = None, max_retries: int = 3,
                     backoff_ms: int = 1000, payload: Any = None) -> Optional[int]:
        """Advanced task with dependencies and scheduling"""
        scheduled = int(time.time() * 1000) + delay_ms
        payload_blob = json.dumps(payload).encode() if payload else None

        with self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Check unique constraint
                if unique_key:
                    cursor = conn.execute("""
                        SELECT id FROM tasks
                        WHERE unique_key = ? AND status IN ('pending', 'leased', 'running')
                    """, (unique_key,))
                    if cursor.fetchone():
                        conn.execute("ROLLBACK")
                        return None

                # Insert task
                cursor = conn.execute("""
                    INSERT INTO tasks (name, command, mode, payload, priority, unique_key,
                                     scheduled_at, max_retries, backoff_ms)
                    VALUES (?, ?, 'advanced', ?, ?, ?, ?, ?, ?)
                """, (name, command, payload_blob, priority, unique_key,
                     scheduled, max_retries, backoff_ms))

                task_id = cursor.lastrowid

                # Add dependencies
                if parent_ids:
                    for parent_id in parent_ids:
                        conn.execute("""
                            INSERT INTO task_deps (child_id, parent_id)
                            VALUES (?, ?)
                        """, (task_id, parent_id))

                conn.execute("COMMIT")
                return task_id

            except Exception as e:
                conn.execute("ROLLBACK")
                raise

    def claim_tasks(self, worker_id: str, limit: int = 1,
                   lease_seconds: int = 300) -> List[Task]:
        """Claim tasks with lease (advanced mode)"""
        now = int(time.time() * 1000)
        lease_until = now + (lease_seconds * 1000)

        with self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Find eligible tasks
                if self.mode == TaskMode.FAST:
                    # Fast mode: simple selection
                    cursor = conn.execute("""
                        SELECT id FROM tasks
                        WHERE status = 'pending'
                        AND mode = 'fast'
                        AND scheduled_at <= ?
                        ORDER BY priority DESC, scheduled_at ASC
                        LIMIT ?
                    """, (now, limit))
                else:
                    # Advanced mode: check dependencies
                    cursor = conn.execute("""
                        SELECT t.id FROM tasks t
                        WHERE t.status = 'pending'
                        AND t.mode = 'advanced'
                        AND t.scheduled_at <= ?
                        AND NOT EXISTS (
                            SELECT 1 FROM task_deps d
                            JOIN tasks p ON p.id = d.parent_id
                            WHERE d.child_id = t.id
                            AND p.status != 'completed'
                        )
                        ORDER BY t.priority DESC, t.id ASC
                        LIMIT ?
                    """, (now, limit))

                task_ids = [row[0] for row in cursor.fetchall()]

                if not task_ids:
                    conn.execute("COMMIT")
                    return []

                # Claim tasks
                placeholders = ','.join('?' * len(task_ids))
                conn.execute(f"""
                    UPDATE tasks
                    SET status = 'leased',
                        lease_until = ?,
                        worker_id = ?,
                        attempts = attempts + 1
                    WHERE id IN ({placeholders})
                """, [lease_until, worker_id] + task_ids)

                # Fetch claimed tasks
                cursor = conn.execute(f"""
                    SELECT * FROM tasks WHERE id IN ({placeholders})
                """, task_ids)

                tasks = []
                for row in cursor.fetchall():
                    tasks.append(Task(
                        id=row['id'],
                        name=row['name'],
                        command=row['command'],
                        mode=TaskMode(row['mode']),
                        payload=json.loads(row['payload']) if row['payload'] else None,
                        priority=row['priority'],
                        status=TaskStatus(row['status']),
                        scheduled_at=row['scheduled_at'],
                        lease_until=row['lease_until'],
                        worker_id=row['worker_id'],
                        attempts=row['attempts'],
                        max_retries=row['max_retries']
                    ))

                conn.execute("COMMIT")
                return tasks

            except Exception as e:
                conn.execute("ROLLBACK")
                raise

    def complete_task(self, task_id: int, success: bool,
                     result: Any = None, error: str = None):
        """Complete or retry task with exponential backoff"""
        now = int(time.time() * 1000)
        status = 'completed' if success else 'failed'
        result_blob = json.dumps(result).encode() if result else None

        with self._get_conn() as conn:
            if success:
                # Mark as completed
                conn.execute("""
                    UPDATE tasks
                    SET status = ?, completed_at = ?, result = ?,
                        lease_until = NULL, worker_id = NULL
                    WHERE id = ?
                """, (status, now, result_blob, task_id))
            else:
                # Check retry eligibility
                cursor = conn.execute("""
                    SELECT attempts, max_retries, backoff_ms, mode
                    FROM tasks WHERE id = ?
                """, (task_id,))
                row = cursor.fetchone()

                if row and row['attempts'] < row['max_retries']:
                    # Calculate exponential backoff
                    if row['mode'] == 'advanced':
                        # Advanced mode: exponential backoff with jitter
                        delay = min(row['backoff_ms'] * (2 ** (row['attempts'] - 1)), 3600000)
                        jitter = int(delay * 0.1)
                        scheduled = now + delay + (hash(task_id) % jitter)
                    else:
                        # Fast mode: simple linear backoff
                        scheduled = now + (row['attempts'] * 5000)

                    conn.execute("""
                        UPDATE tasks
                        SET status = 'pending', scheduled_at = ?,
                            lease_until = NULL, worker_id = NULL
                        WHERE id = ?
                    """, (scheduled, task_id))
                else:
                    # Permanently failed
                    conn.execute("""
                        UPDATE tasks
                        SET status = 'failed', completed_at = ?, error = ?,
                            lease_until = NULL, worker_id = NULL
                        WHERE id = ?
                    """, (now, error[:1000] if error else None, task_id))

            conn.commit()

    def reclaim_expired_leases(self) -> int:
        """Reclaim tasks with expired leases"""
        now = int(time.time() * 1000)
        with self._get_conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks
                SET status = 'pending',
                    lease_until = NULL,
                    worker_id = NULL
                WHERE status = 'leased' AND lease_until < ?
            """, (now,))
            conn.commit()
            return cursor.rowcount

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT
                    mode,
                    status,
                    COUNT(*) as count
                FROM tasks
                GROUP BY mode, status
            """)

            stats = {'fast': {}, 'advanced': {}, 'total': {}}
            for row in cursor.fetchall():
                stats[row['mode']][row['status']] = row['count']
                stats['total'][row['status']] = stats['total'].get(row['status'], 0) + row['count']

            # Check expired leases
            cursor = conn.execute("""
                SELECT COUNT(*) as expired
                FROM tasks
                WHERE status = 'leased' AND lease_until < ?
            """, (int(time.time() * 1000),))
            stats['expired_leases'] = cursor.fetchone()['expired']

            return stats

class HybridWorker:
    """Worker supporting both fast and advanced modes"""

    def __init__(self, queue: HybridTaskQueue, worker_id: str = None,
                 mode: TaskMode = TaskMode.FAST):
        self.queue = queue
        self.worker_id = worker_id or f"worker-{os.getpid()}"
        self.mode = mode
        self.running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        """Graceful shutdown"""
        print(f"Worker {self.worker_id} shutting down...")
        self.running = False

    def run_fast(self):
        """Fast worker loop (claude1 style)"""
        print(f"Fast worker {self.worker_id} started")

        while self.running:
            task = self.queue.pop_fast()
            if task:
                print(f"[FAST] Running: {task['name']}")
                try:
                    result = subprocess.run(
                        task['command'],
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    success = result.returncode == 0
                    self.queue.complete_task(
                        task['id'],
                        success,
                        {'stdout': result.stdout, 'stderr': result.stderr}
                    )
                    print(f"[FAST] {'Success' if success else 'Failed'}: {task['name']}")
                except Exception as e:
                    self.queue.complete_task(task['id'], False, error=str(e))
                    print(f"[FAST] Error: {task['name']} - {e}")
            else:
                time.sleep(0.1)  # Brief sleep when empty

    def run_advanced(self, batch_size: int = 1, lease_seconds: int = 300):
        """Advanced worker loop (claudeCode2 style)"""
        print(f"Advanced worker {self.worker_id} started (batch={batch_size})")

        while self.running:
            try:
                # Reclaim expired leases
                reclaimed = self.queue.reclaim_expired_leases()
                if reclaimed:
                    print(f"[ADV] Reclaimed {reclaimed} expired leases")

                # Claim tasks
                tasks = self.queue.claim_tasks(self.worker_id, batch_size, lease_seconds)

                for task in tasks:
                    if not self.running:
                        break

                    print(f"[ADV] Executing: {task.name} (attempt {task.attempts}/{task.max_retries})")

                    # Record run
                    with self.queue._get_conn() as conn:
                        cursor = conn.execute("""
                            INSERT INTO task_runs (task_id, worker_id)
                            VALUES (?, ?)
                        """, (task.id, self.worker_id))
                        run_id = cursor.lastrowid
                        conn.commit()

                    try:
                        # Execute with timeout
                        result = subprocess.run(
                            task.command,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=lease_seconds - 10
                        )

                        # Update run record
                        with self.queue._get_conn() as conn:
                            conn.execute("""
                                UPDATE task_runs
                                SET ended_at = ?, exit_code = ?, output = ?
                                WHERE id = ?
                            """, (int(time.time() * 1000), result.returncode,
                                 json.dumps({'stdout': result.stdout[:5000],
                                           'stderr': result.stderr[:5000]}),
                                 run_id))
                            conn.commit()

                        self.queue.complete_task(
                            task.id,
                            result.returncode == 0,
                            {'stdout': result.stdout, 'stderr': result.stderr},
                            result.stderr if result.returncode != 0 else None
                        )

                        status = "succeeded" if result.returncode == 0 else "failed"
                        print(f"[ADV] Task {task.name} {status} (exit={result.returncode})")

                    except subprocess.TimeoutExpired:
                        self.queue.complete_task(task.id, False, error="TIMEOUT")
                        print(f"[ADV] Task {task.name} timed out")

                    except Exception as e:
                        self.queue.complete_task(task.id, False, error=str(e))
                        print(f"[ADV] Task {task.name} error: {e}")

                if not tasks:
                    time.sleep(1)

            except Exception as e:
                print(f"[ADV] Worker error: {e}")
                time.sleep(5)

    def run(self, batch_size: int = 1):
        """Run worker in configured mode"""
        if self.mode == TaskMode.FAST:
            self.run_fast()
        else:
            self.run_advanced(batch_size)

class SystemdIntegration:
    """Systemd service management"""

    def __init__(self):
        self.unit_prefix = UNIT_PREFIX

    def create_worker_service(self, mode: TaskMode = TaskMode.FAST,
                            batch_size: int = 1) -> str:
        """Create systemd service for worker"""
        script_path = Path(__file__).absolute()
        unit_name = f"{self.unit_prefix}worker-{mode.value}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)

        unit_content = f"""[Unit]
Description=AIOS Hybrid Worker ({mode.value} mode)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {script_path} worker --mode {mode.value} --batch {batch_size}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=10

[Install]
WantedBy=default.target
"""
        unit_path.write_text(unit_content)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        return unit_name

    def start_worker(self, mode: TaskMode = TaskMode.FAST):
        """Start worker service"""
        unit_name = f"{self.unit_prefix}worker-{mode.value}.service"
        subprocess.run(["systemctl", "--user", "start", unit_name], check=False)
        print(f"Started {unit_name}")

    def stop_worker(self, mode: TaskMode = TaskMode.FAST):
        """Stop worker service"""
        unit_name = f"{self.unit_prefix}worker-{mode.value}.service"
        subprocess.run(["systemctl", "--user", "stop", unit_name], check=False)
        print(f"Stopped {unit_name}")

def benchmark():
    """Benchmark both modes"""
    print("=== ClaudeCodeA Hybrid Benchmark ===\n")

    # Test fast mode
    queue_fast = HybridTaskQueue(mode=TaskMode.FAST)
    print("Testing FAST mode (claude1 style)...")
    start = time.perf_counter()

    for i in range(100):
        queue_fast.push_fast(f"fast_task_{i}", f"echo 'Fast {i}'", priority=i % 3)

    fast_time = (time.perf_counter() - start) * 1000
    print(f"Fast mode: 100 tasks in {fast_time:.2f}ms ({fast_time/100:.3f}ms per task)\n")

    # Test advanced mode
    queue_adv = HybridTaskQueue(mode=TaskMode.ADVANCED)
    print("Testing ADVANCED mode (claudeCode2 style)...")
    start = time.perf_counter()

    # Create parent task
    parent_id = queue_adv.push_advanced("parent", "echo 'Parent'", priority=10)

    # Create child tasks with dependencies
    for i in range(99):
        queue_adv.push_advanced(
            f"adv_task_{i}",
            f"echo 'Advanced {i}'",
            priority=i % 3,
            parent_ids=[parent_id] if i < 10 else None,
            unique_key=f"unique_{i}" if i % 10 == 0 else None
        )

    adv_time = (time.perf_counter() - start) * 1000
    print(f"Advanced mode: 100 tasks in {adv_time:.2f}ms ({adv_time/100:.3f}ms per task)\n")

    # Show stats
    print("Fast mode stats:", queue_fast.get_stats())
    print("Advanced mode stats:", queue_adv.get_stats())

    return fast_time, adv_time

def main():
    """CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description="ClaudeCodeA Hybrid Task Orchestrator")
    parser.add_argument("command", choices=["add", "worker", "stats", "test", "benchmark",
                                           "install", "start", "stop"])
    parser.add_argument("--mode", choices=["fast", "advanced"], default="fast",
                       help="Operating mode")
    parser.add_argument("--name", help="Task name")
    parser.add_argument("--cmd", help="Task command")
    parser.add_argument("--priority", type=int, default=0, help="Task priority")
    parser.add_argument("--delay", type=int, default=0, help="Delay in milliseconds")
    parser.add_argument("--batch", type=int, default=1, help="Batch size for worker")
    parser.add_argument("--unique", help="Unique key for deduplication")
    parser.add_argument("--parent", type=int, action="append", help="Parent task IDs")

    args = parser.parse_args()

    # Initialize queue with selected mode
    mode = TaskMode.FAST if args.mode == "fast" else TaskMode.ADVANCED
    queue = HybridTaskQueue(mode=mode)

    if args.command == "add":
        if not args.name or not args.cmd:
            print("Error: --name and --cmd required")
            sys.exit(1)

        if mode == TaskMode.FAST:
            task_id = queue.push_fast(args.name, args.cmd, args.priority)
        else:
            task_id = queue.push_advanced(
                args.name, args.cmd,
                priority=args.priority,
                delay_ms=args.delay,
                unique_key=args.unique,
                parent_ids=args.parent
            )

        if task_id:
            print(f"Added task {task_id} in {mode.value} mode")
        else:
            print("Task not added (duplicate unique key?)")

    elif args.command == "worker":
        worker = HybridWorker(queue, mode=mode)
        worker.run(args.batch)

    elif args.command == "stats":
        stats = queue.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.command == "test":
        print(f"Creating test workflow in {mode.value} mode...")

        if mode == TaskMode.FAST:
            # Fast mode test
            for i in range(5):
                task_id = queue.push_fast(f"test_fast_{i}", f"echo 'Fast test {i}'", i)
                print(f"Added fast task {task_id}")
        else:
            # Advanced mode test with dependencies
            parent = queue.push_advanced("test_setup", "echo 'Setting up test...'", priority=10)
            print(f"Parent task: {parent}")

            for i in range(3):
                child = queue.push_advanced(
                    f"test_process_{i}",
                    f"echo 'Processing {i}'",
                    priority=5,
                    parent_ids=[parent]
                )
                print(f"Child task {i}: {child}")

            # Delayed cleanup
            cleanup = queue.push_advanced(
                "test_cleanup",
                "echo 'Cleaning up...'",
                delay_ms=5000,
                unique_key="cleanup_test"
            )
            print(f"Cleanup task: {cleanup}")

        print(f"\nRun 'worker --mode {args.mode}' to process tasks")

    elif args.command == "benchmark":
        benchmark()

    elif args.command == "install":
        systemd = SystemdIntegration()
        unit_name = systemd.create_worker_service(mode, args.batch)
        print(f"Installed systemd service: {unit_name}")
        print(f"Start with: systemctl --user start {unit_name}")

    elif args.command == "start":
        systemd = SystemdIntegration()
        systemd.start_worker(mode)

    elif args.command == "stop":
        systemd = SystemdIntegration()
        systemd.stop_worker(mode)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()