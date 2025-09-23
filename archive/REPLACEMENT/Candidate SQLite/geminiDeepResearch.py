#!/usr/bin/env python3
"""
AIOS_TaskQueue: A high-performance, persistent SQLite-based task queue for AIOS.

This module provides a thread-safe and process-safe task queue using SQLite,
designed for reliability and performance in a single-node environment. It leverages
modern SQLite features like WAL mode and atomic updates to handle concurrency
safely and efficiently.
"""
import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Union

class AIOS_TaskQueue:
    """
    A robust SQLite-backed task queue with an acknowledgment protocol.

    This queue implements an atomic dequeue operation to prevent race conditions
    and a multi-stage acknowledgment system (ack/nack/fail) to ensure tasks
    are not lost if a worker fails.
    """

    _CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS aios_tasks (
        id INTEGER PRIMARY KEY,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        priority INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'now')),
        claimed_at TEXT
    );
    """
    _CREATE_INDEX_SQL = """
    CREATE INDEX IF NOT EXISTS idx_tasks_status_priority_created_at
    ON aios_tasks (status, priority, created_at);
    """

    _DEQUEUE_SQL = """
    UPDATE aios_tasks
    SET
        status = 'in_progress',
        claimed_at = STRFTIME('%Y-%m-%d %H:%M:%f', 'now'),
        attempts = attempts + 1
    WHERE
        id = (
            SELECT id
            FROM aios_tasks
            WHERE status = 'pending' AND attempts < max_attempts
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        )
    RETURNING *;
    """

    def __init__(self, db_path: Union[str, Path], worker_id: str = "default"):
        """
        Initializes the task queue.

        Args:
            db_path: Path to the SQLite database file.
            worker_id: A unique identifier for the worker instance using this queue.
        """
        self.db_path = Path(db_path)
        self.worker_id = worker_id
        self._local = threading.local()  # For thread-local connection storage

        # The initial connection is just to set up the database.
        # Each thread will get its own connection from the pool on first use.
        with self._connect() as conn:
            conn.execute(self._CREATE_TABLE_SQL)
            conn.execute(self._CREATE_INDEX_SQL)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """
        Establishes and configures a new SQLite connection.
        This connection is configured for high performance and concurrency.
        """
        try:
            # Use a thread-local connection to avoid sharing connections across threads
            # without proper locking, which is safer.
            return self._local.conn
        except AttributeError:
            # WAL mode is crucial for allowing concurrent reads and writes.
            # It prevents producers from being locked out by consumers.
            uri = f"file:{self.db_path}?mode=rwc"
            conn = sqlite3.connect(uri, uri=True, timeout=10, check_same_thread=False)
            conn.row_factory = sqlite3.Row

            # Apply performance and reliability PRAGMAs
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA mmap_size=268435456;") # 256 MB mmap
            
            self._local.conn = conn
            return conn

    def enqueue(self, payload: str, priority: int = 0, max_attempts: int = 3) -> int:
        """
        Adds a new task to the queue.

        Args:
            payload: The task data, typically a JSON string.
            priority: Task priority (higher numbers are processed first).
            max_attempts: Maximum number of times to retry the task.

        Returns:
            The ID of the newly enqueued task.
        """
        sql = """
        INSERT INTO aios_tasks (payload, priority, max_attempts)
        VALUES (?,?,?);
        """
        with self._connect() as conn:
            cursor = conn.execute(sql, (payload, priority, max_attempts))
            conn.commit()
            return cursor.lastrowid

    def dequeue(self) -> Optional]:
        """
        Atomically retrieves and claims the next available task from the queue.

        This method is safe from race conditions between multiple workers.

        Returns:
            A dictionary representing the task, or None if the queue is empty.
        """
        with self._connect() as conn:
            cursor = conn.execute(self._DEQUEUE_SQL)
            row = cursor.fetchone()
            conn.commit()
            return dict(row) if row else None

    def ack(self, task_id: int) -> bool:
        """
        Acknowledges successful completion of a task, removing it from the queue.

        Args:
            task_id: The ID of the task to acknowledge.
        
        Returns:
            True if a row was deleted, False otherwise.
        """
        sql = "DELETE FROM aios_tasks WHERE id =?;"
        with self._connect() as conn:
            cursor = conn.execute(sql, (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def nack(self, task_id: int) -> bool:
        """
        Negative acknowledgment. Returns a task to the 'pending' state for retry.

        If the task has exceeded its max_attempts, it will be moved to 'failed'.

        Args:
            task_id: The ID of the task to NACK.
            
        Returns:
            True if the task was successfully NACKed or failed, False otherwise.
        """
        with self._connect() as conn:
            # First, get current attempts and max_attempts
            cursor = conn.execute("SELECT attempts, max_attempts FROM aios_tasks WHERE id =?", (task_id,))
            task_info = cursor.fetchone()

            if not task_info:
                return False

            if task_info['attempts'] >= task_info['max_attempts']:
                # Max attempts reached, move to failed state
                return self.fail(task_id)
            else:
                # Reset to pending for another worker to pick up
                sql = "UPDATE aios_tasks SET status = 'pending', claimed_at = NULL WHERE id =?;"
                cursor = conn.execute(sql, (task_id,))
                conn.commit()
                return cursor.rowcount > 0

    def fail(self, task_id: int) -> bool:
        """
        Marks a task as 'failed' after exhausting retries or for a fatal error.

        Failed tasks are preserved for inspection but are not processed again.

        Args:
            task_id: The ID of the task to mark as failed.
            
        Returns:
            True if a row was updated, False otherwise.
        """
        sql = "UPDATE aios_tasks SET status = 'failed' WHERE id =?;"
        with self._connect() as conn:
            cursor = conn.execute(sql, (task_id,))
            conn.commit()
            return cursor.rowcount > 0
            
    def requeue_stale(self, timeout_seconds: int = 300) -> int:
        """
        Finds and requeues tasks that have been 'in_progress' for too long.

        This is a self-healing mechanism to handle worker crashes.

        Args:
            timeout_seconds: The number of seconds after which a task is considered stale.

        Returns:
            The number of tasks that were requeued.
        """
        sql = f"""
        UPDATE aios_tasks
        SET status = 'pending', claimed_at = NULL
        WHERE
            status = 'in_progress'
            AND STRFTIME('%s', 'now') - STRFTIME('%s', claimed_at) >?;
        """
        with self._connect() as conn:
            cursor = conn.execute(sql, (timeout_seconds,))
            requeued_count = cursor.rowcount
            conn.commit()
            return requeued_count
    
    def qsize(self) -> int:
        """Returns the number of tasks currently in 'pending' state."""
        sql = "SELECT COUNT(*) FROM aios_tasks WHERE status = 'pending';"
        with self._connect() as conn:
            return conn.execute(sql).fetchone()

    def close(self):
        """Closes the thread-local database connection."""
        try:
            if self._local.conn:
                self._local.conn.close()
                self._local.conn = None
        except AttributeError:
            pass