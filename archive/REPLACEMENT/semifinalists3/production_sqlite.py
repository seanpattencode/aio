#!/usr/bin/env python3
"""
Production SQLite Task Queue System
Synthesized from Firefox, Chrome, Android, Signal implementations
Handles 500M+ device scale patterns
"""

import sqlite3
import json
import time
import threading
import queue
import hashlib
import logging
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from datetime import datetime, timedelta
import signal
import sys

# Configuration from production systems
class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"

class TaskPriority(Enum):
    USER_BLOCKING = 100  # Firefox pattern
    USER_VISIBLE = 50
    BACKGROUND = 0

@dataclass
class Task:
    """Task model based on Android WorkManager and Chrome patterns"""
    id: Optional[int] = None
    type: str = ""
    payload: Dict[str, Any] = None
    status: str = TaskStatus.PENDING.value
    priority: int = TaskPriority.BACKGROUND.value
    created_at: Optional[float] = None
    scheduled_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    backoff_policy: str = "exponential"  # Android pattern
    backoff_delay: float = 1.0
    error_message: Optional[str] = None
    worker_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    dependencies: List[int] = None

    def __post_init__(self):
        if self.payload is None:
            self.payload = {}
        if self.dependencies is None:
            self.dependencies = []
        if self.created_at is None:
            self.created_at = time.time()

class SQLiteConnectionPool:
    """Connection pooling based on Chrome and Android patterns"""

    def __init__(self, db_path: str, max_connections: int = 4):  # Android default
        self.db_path = db_path
        self.pool = queue.Queue(maxsize=max_connections)
        self.lock = threading.Lock()

        # Pre-create connections
        for _ in range(max_connections):
            conn = self._create_connection()
            self.pool.put(conn)

    def _create_connection(self) -> sqlite3.Connection:
        """Create optimized connection with production PRAGMA settings"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0,  # Chrome pattern
            isolation_level=None  # Manual transaction control
        )

        # Apply production optimizations from all systems
        pragmas = [
            "PRAGMA journal_mode=WAL",  # Universal pattern
            "PRAGMA synchronous=NORMAL",  # Safe with WAL
            "PRAGMA cache_size=-8000",  # 8MB cache (Chrome)
            "PRAGMA temp_store=MEMORY",
            "PRAGMA mmap_size=268435456",  # 256MB (Chrome)
            "PRAGMA busy_timeout=5000",  # 5 second timeout
            "PRAGMA wal_autocheckpoint=1000",  # Firefox pattern
            "PRAGMA page_size=4096",  # Chrome uses 4KB
        ]

        for pragma in pragmas:
            conn.execute(pragma)

        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def get_connection(self):
        """Thread-safe connection checkout"""
        conn = self.pool.get()
        try:
            yield conn
        finally:
            # Return to pool
            self.pool.put(conn)

class TaskQueue:
    """Production task queue synthesizing patterns from major implementations"""

    def __init__(self, db_path: str = "tasks.db", max_connections: int = 4):
        self.db_path = db_path
        self.pool = SQLiteConnectionPool(db_path, max_connections)
        self.logger = logging.getLogger(__name__)
        self._shutdown = False
        self._worker_threads = []
        self._setup_database()
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Graceful shutdown like Firefox background tasks"""
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self._shutdown = True

    def _setup_database(self):
        """Initialize schema based on production patterns"""
        with self.pool.get_connection() as conn:
            # Main tasks table (combining patterns from all systems)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    payload TEXT,
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (julianday('now')),
                    scheduled_at REAL,
                    started_at REAL,
                    completed_at REAL,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    backoff_policy TEXT DEFAULT 'exponential',
                    backoff_delay REAL DEFAULT 1.0,
                    error_message TEXT,
                    worker_id TEXT,
                    result TEXT,

                    -- Chrome download manager pattern
                    state_transition_count INTEGER DEFAULT 0,
                    last_modified REAL DEFAULT (julianday('now')),

                    -- Android WorkManager pattern
                    required_network_type INTEGER DEFAULT 0,
                    requires_charging INTEGER DEFAULT 0,
                    requires_device_idle INTEGER DEFAULT 0
                )
            """)

            # Dependencies table (Android WorkManager pattern)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    task_id INTEGER,
                    depends_on_id INTEGER,
                    PRIMARY KEY (task_id, depends_on_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (depends_on_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)

            # Error tracking (Signal/Firefox pattern)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    error_message TEXT,
                    stack_trace TEXT,
                    occurred_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)

            # Performance metrics table (Chrome pattern)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_metrics (
                    task_id INTEGER PRIMARY KEY,
                    queue_time REAL,
                    execution_time REAL,
                    total_time REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)

            # Create optimized indexes (composite index pattern from all systems)
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_tasks_queue ON tasks(status, priority DESC, created_at ASC)",
                "CREATE INDEX IF NOT EXISTS idx_tasks_scheduled ON tasks(scheduled_at) WHERE scheduled_at IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_tasks_type_status ON tasks(type, status)",
                "CREATE INDEX IF NOT EXISTS idx_tasks_worker ON tasks(worker_id) WHERE worker_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_deps_task ON task_dependencies(task_id)",
                "CREATE INDEX IF NOT EXISTS idx_deps_depends ON task_dependencies(depends_on_id)"
            ]

            for idx in indexes:
                conn.execute(idx)

            conn.execute("COMMIT")

    def enqueue(self, task: Task) -> int:
        """Enqueue task with Chrome/Firefox transaction patterns"""
        with self.pool.get_connection() as conn:
            # Chrome pattern: track state transitions
            task_dict = asdict(task)

            # Serialize complex fields
            task_dict['payload'] = json.dumps(task_dict['payload'])
            if task_dict['result']:
                task_dict['result'] = json.dumps(task_dict['result'])

            dependencies = task_dict.pop('dependencies', [])
            task_dict.pop('id', None)  # Let DB assign ID

            # Use IMMEDIATE transaction (Firefox pattern to prevent deadlocks)
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    f"""INSERT INTO tasks ({','.join(task_dict.keys())})
                        VALUES ({','.join(['?' for _ in task_dict])})""",
                    list(task_dict.values())
                )
                task_id = cursor.lastrowid

                # Add dependencies if any (Android WorkManager pattern)
                for dep_id in dependencies:
                    conn.execute(
                        "INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (?, ?)",
                        (task_id, dep_id)
                    )

                conn.execute("COMMIT")
                self.logger.debug(f"Enqueued task {task_id} of type {task.type}")
                return task_id

            except Exception as e:
                conn.execute("ROLLBACK")
                self.logger.error(f"Failed to enqueue task: {e}")
                raise

    def dequeue(self, worker_id: str, task_types: Optional[List[str]] = None) -> Optional[Task]:
        """Atomic dequeue with Chrome's state machine pattern"""
        with self.pool.get_connection() as conn:
            # Use IMMEDIATE to prevent lock escalation deadlocks
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Check for scheduled tasks first (Android pattern)
                current_time = time.time()
                julian_now = datetime.fromtimestamp(current_time).toordinal() + 1721425.5

                # Build query with optional type filter
                query = """
                    SELECT t.* FROM tasks t
                    LEFT JOIN task_dependencies d ON t.id = d.task_id
                    WHERE t.status IN ('pending', 'scheduled')
                    AND (t.scheduled_at IS NULL OR t.scheduled_at <= ?)
                    AND d.task_id IS NULL  -- No pending dependencies
                """

                params = [julian_now]
                if task_types:
                    placeholders = ','.join(['?' for _ in task_types])
                    query += f" AND t.type IN ({placeholders})"
                    params.extend(task_types)

                query += " ORDER BY t.priority DESC, t.created_at ASC LIMIT 1"

                cursor = conn.execute(query, params)
                row = cursor.fetchone()

                if row:
                    task_id = row['id']

                    # Check if dependencies are satisfied (Android WorkManager)
                    deps = conn.execute("""
                        SELECT d.depends_on_id, t.status
                        FROM task_dependencies d
                        JOIN tasks t ON d.depends_on_id = t.id
                        WHERE d.task_id = ?
                    """, (task_id,)).fetchall()

                    if any(dep['status'] != 'completed' for dep in deps):
                        conn.execute("ROLLBACK")
                        return None  # Dependencies not satisfied

                    # Atomic claim (Chrome download manager pattern)
                    result = conn.execute("""
                        UPDATE tasks
                        SET status = 'processing',
                            worker_id = ?,
                            started_at = julianday('now'),
                            state_transition_count = state_transition_count + 1,
                            last_modified = julianday('now')
                        WHERE id = ? AND status IN ('pending', 'scheduled')
                    """, (worker_id, task_id))

                    if result.rowcount > 0:
                        conn.execute("COMMIT")
                        return self._row_to_task(row)

                conn.execute("ROLLBACK")
                return None

            except Exception as e:
                conn.execute("ROLLBACK")
                self.logger.error(f"Dequeue failed: {e}")
                raise

    def complete_task(self, task_id: int, result: Optional[Dict[str, Any]] = None):
        """Complete task with Chrome's state tracking"""
        with self.pool.get_connection() as conn:
            result_json = json.dumps(result) if result else None

            # Record metrics (Chrome pattern)
            metrics = conn.execute("""
                SELECT created_at, started_at FROM tasks WHERE id = ?
            """, (task_id,)).fetchone()

            if metrics:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    # Update task status
                    conn.execute("""
                        UPDATE tasks
                        SET status = 'completed',
                            completed_at = julianday('now'),
                            result = ?,
                            state_transition_count = state_transition_count + 1,
                            last_modified = julianday('now')
                        WHERE id = ?
                    """, (result_json, task_id))

                    # Record performance metrics
                    julian_now = datetime.now().toordinal() + 1721425.5
                    queue_time = metrics['started_at'] - metrics['created_at'] if metrics['started_at'] else 0
                    exec_time = julian_now - metrics['started_at'] if metrics['started_at'] else 0

                    conn.execute("""
                        INSERT OR REPLACE INTO task_metrics
                        (task_id, queue_time, execution_time, total_time)
                        VALUES (?, ?, ?, ?)
                    """, (task_id, queue_time, exec_time, queue_time + exec_time))

                    conn.execute("COMMIT")

                except Exception as e:
                    conn.execute("ROLLBACK")
                    raise

    def fail_task(self, task_id: int, error_message: str, retry: bool = True):
        """Fail task with retry logic (Android/Signal pattern)"""
        with self.pool.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Get current task state
                task = conn.execute("""
                    SELECT retry_count, max_retries, backoff_policy, backoff_delay
                    FROM tasks WHERE id = ?
                """, (task_id,)).fetchone()

                if not task:
                    conn.execute("ROLLBACK")
                    return

                # Record error (Signal pattern)
                conn.execute("""
                    INSERT INTO task_errors (task_id, error_message)
                    VALUES (?, ?)
                """, (task_id, error_message))

                if retry and task['retry_count'] < task['max_retries']:
                    # Calculate backoff (Android pattern)
                    if task['backoff_policy'] == 'exponential':
                        delay = task['backoff_delay'] * (2 ** task['retry_count'])
                    else:  # linear
                        delay = task['backoff_delay'] * (task['retry_count'] + 1)

                    scheduled_at = datetime.fromtimestamp(time.time() + delay).toordinal() + 1721425.5

                    # Reschedule with backoff
                    conn.execute("""
                        UPDATE tasks
                        SET status = 'scheduled',
                            scheduled_at = ?,
                            retry_count = retry_count + 1,
                            error_message = ?,
                            worker_id = NULL,
                            state_transition_count = state_transition_count + 1,
                            last_modified = julianday('now')
                        WHERE id = ?
                    """, (scheduled_at, error_message, task_id))
                else:
                    # Final failure
                    conn.execute("""
                        UPDATE tasks
                        SET status = 'failed',
                            error_message = ?,
                            completed_at = julianday('now'),
                            state_transition_count = state_transition_count + 1,
                            last_modified = julianday('now')
                        WHERE id = ?
                    """, (error_message, task_id))

                conn.execute("COMMIT")

            except Exception as e:
                conn.execute("ROLLBACK")
                self.logger.error(f"Failed to fail task: {e}")
                raise

    def get_task_status(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get task status with full details"""
        with self.pool.get_connection() as conn:
            row = conn.execute("""
                SELECT t.*,
                       m.queue_time, m.execution_time, m.total_time
                FROM tasks t
                LEFT JOIN task_metrics m ON t.id = m.task_id
                WHERE t.id = ?
            """, (task_id,)).fetchone()

            if row:
                return dict(row)
            return None

    def cleanup_old_tasks(self, days: int = 7):
        """Cleanup pattern from Chrome/Firefox"""
        with self.pool.get_connection() as conn:
            cutoff = datetime.fromtimestamp(time.time() - (days * 86400)).toordinal() + 1721425.5

            conn.execute("BEGIN IMMEDIATE")
            try:
                # Delete completed/failed tasks
                result = conn.execute("""
                    DELETE FROM tasks
                    WHERE status IN ('completed', 'failed', 'cancelled')
                    AND completed_at < ?
                """, (cutoff,))

                deleted = result.rowcount

                # Check fragmentation (Firefox pattern)
                stats = conn.execute("""
                    SELECT page_count, freelist_count FROM pragma_page_count(), pragma_freelist_count()
                """).fetchone()

                if stats and stats['freelist_count'] > stats['page_count'] * 0.3:
                    # Vacuum if >30% fragmented
                    conn.execute("COMMIT")
                    conn.execute("VACUUM")
                else:
                    conn.execute("COMMIT")

                self.logger.info(f"Cleaned up {deleted} old tasks")

            except Exception as e:
                conn.execute("ROLLBACK")
                self.logger.error(f"Cleanup failed: {e}")
                raise

    def checkpoint_wal(self, mode: str = "PASSIVE"):
        """WAL checkpoint management (Firefox pattern)"""
        with self.pool.get_connection() as conn:
            result = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
            self.logger.debug(f"WAL checkpoint: {result}")
            return result

    def get_metrics(self) -> Dict[str, Any]:
        """Performance metrics (Chrome pattern)"""
        with self.pool.get_connection() as conn:
            metrics = {}

            # Task counts by status
            status_counts = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM tasks
                GROUP BY status
            """).fetchall()
            metrics['status_counts'] = {row['status']: row['count'] for row in status_counts}

            # Performance stats
            perf = conn.execute("""
                SELECT
                    AVG(queue_time) as avg_queue_time,
                    AVG(execution_time) as avg_exec_time,
                    MAX(queue_time) as max_queue_time,
                    MAX(execution_time) as max_exec_time
                FROM task_metrics
            """).fetchone()

            if perf:
                metrics['performance'] = dict(perf)

            # Database stats
            db_stats = conn.execute("""
                SELECT page_count * page_size as db_size,
                       freelist_count * page_size as free_size
                FROM pragma_page_count(), pragma_page_size(), pragma_freelist_count()
            """).fetchone()

            if db_stats:
                metrics['database'] = dict(db_stats)

            # WAL status
            wal = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            metrics['wal_pages'] = wal[1] if wal else 0

            return metrics

    def recover_stalled_tasks(self, timeout_seconds: int = 3600):
        """Recover stalled tasks (Android pattern)"""
        with self.pool.get_connection() as conn:
            cutoff = datetime.fromtimestamp(time.time() - timeout_seconds).toordinal() + 1721425.5

            result = conn.execute("""
                UPDATE tasks
                SET status = 'pending',
                    worker_id = NULL,
                    error_message = 'Task stalled and recovered'
                WHERE status = 'processing'
                AND started_at < ?
            """, (cutoff,))

            recovered = result.rowcount
            if recovered > 0:
                self.logger.info(f"Recovered {recovered} stalled tasks")

            return recovered

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert database row to Task object"""
        task_dict = dict(row)

        # Deserialize JSON fields
        if task_dict.get('payload'):
            task_dict['payload'] = json.loads(task_dict['payload'])
        if task_dict.get('result'):
            task_dict['result'] = json.loads(task_dict['result'])

        # Convert Julian dates to Unix timestamps
        for field in ['created_at', 'scheduled_at', 'started_at', 'completed_at']:
            if task_dict.get(field):
                # Julian date to Unix timestamp
                dt = datetime.fromordinal(int(task_dict[field] - 1721425.5))
                task_dict[field] = dt.timestamp()

        # Remove non-Task fields
        for key in ['state_transition_count', 'last_modified',
                   'required_network_type', 'requires_charging', 'requires_device_idle']:
            task_dict.pop(key, None)

        return Task(**task_dict)

    def schedule_recurring_task(self, task: Task, interval_seconds: int):
        """Schedule recurring task (Android WorkManager pattern)"""
        task.scheduled_at = time.time() + interval_seconds
        task_id = self.enqueue(task)

        # Store recurrence info in payload
        task.payload['_recurrence_interval'] = interval_seconds
        task.payload['_recurrence_original_id'] = task_id

        with self.pool.get_connection() as conn:
            conn.execute("""
                UPDATE tasks
                SET payload = ?
                WHERE id = ?
            """, (json.dumps(task.payload), task_id))

        return task_id

# Worker implementation
class TaskWorker(threading.Thread):
    """Worker thread implementation based on production patterns"""

    def __init__(self, queue: TaskQueue, worker_id: str, task_types: Optional[List[str]] = None):
        super().__init__(daemon=True)
        self.queue = queue
        self.worker_id = worker_id
        self.task_types = task_types
        self.logger = logging.getLogger(f"{__name__}.{worker_id}")
        self._stop_event = threading.Event()

    def run(self):
        """Main worker loop with Signal/Android patterns"""
        self.logger.info(f"Worker {self.worker_id} started")

        while not self._stop_event.is_set():
            try:
                # Dequeue task
                task = self.queue.dequeue(self.worker_id, self.task_types)

                if not task:
                    # No task available, wait briefly
                    time.sleep(0.1)
                    continue

                self.logger.debug(f"Processing task {task.id} of type {task.type}")

                try:
                    # Process task (implement your logic here)
                    result = self.process_task(task)

                    # Check for recurrence (Android pattern)
                    if task.payload.get('_recurrence_interval'):
                        # Schedule next occurrence
                        new_task = Task(
                            type=task.type,
                            payload={k: v for k, v in task.payload.items()
                                   if not k.startswith('_')},
                            priority=task.priority,
                            scheduled_at=time.time() + task.payload['_recurrence_interval']
                        )
                        new_task.payload['_recurrence_interval'] = task.payload['_recurrence_interval']
                        self.queue.enqueue(new_task)

                    self.queue.complete_task(task.id, result)

                except Exception as e:
                    self.logger.error(f"Task {task.id} failed: {e}")
                    self.queue.fail_task(task.id, str(e))

            except Exception as e:
                self.logger.error(f"Worker error: {e}")
                time.sleep(1)  # Brief pause on error

    def process_task(self, task: Task) -> Dict[str, Any]:
        """Override this method to implement task processing"""
        # Placeholder implementation
        self.logger.info(f"Processing task {task.id}: {task.payload}")
        time.sleep(0.1)  # Simulate work
        return {"success": True, "processed_at": time.time()}

    def stop(self):
        """Stop worker gracefully"""
        self._stop_event.set()

# Example usage compatible with systemd orchestrator
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize queue
    queue = TaskQueue("aios_tasks.db")

    # Start workers
    workers = []
    for i in range(4):  # Android default connection pool size
        worker = TaskWorker(queue, f"worker-{i}")
        worker.start()
        workers.append(worker)

    # Example task creation
    task = Task(
        type="ai_workflow",
        payload={"workflow_id": "123", "action": "process"},
        priority=TaskPriority.USER_VISIBLE.value
    )
    task_id = queue.enqueue(task)

    # Maintenance loop
    last_cleanup = time.time()
    last_checkpoint = time.time()

    try:
        while True:
            # Periodic maintenance (Firefox/Chrome patterns)
            if time.time() - last_cleanup > 3600:  # Hourly
                queue.cleanup_old_tasks()
                queue.recover_stalled_tasks()
                last_cleanup = time.time()

            if time.time() - last_checkpoint > 300:  # 5 minutes
                queue.checkpoint_wal()
                last_checkpoint = time.time()

            # Log metrics
            metrics = queue.get_metrics()
            logging.info(f"Queue metrics: {metrics}")

            time.sleep(60)  # Check every minute

    except KeyboardInterrupt:
        logging.info("Shutting down...")
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=5)