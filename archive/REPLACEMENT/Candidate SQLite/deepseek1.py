import sqlite3
import threading
import time
import json
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class SQLiteTaskQueue:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
        self.lock = threading.RLock()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
                    metadata TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON tasks(priority DESC)")
            conn.commit()

    def add_task(self, name: str, command: str, priority: int = 0, 
                 metadata: Optional[Dict] = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            meta_json = json.dumps(metadata) if metadata else None
            cursor.execute(
                "INSERT INTO tasks (name, command, priority, metadata) VALUES (?, ?, ?, ?)",
                (name, command, priority, meta_json)
            )
            conn.commit()
            return cursor.lastrowid

    def get_next_task(self) -> Optional[Dict[str, Any]]:
        with self.lock, sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Find the next pending task with highest priority
            cursor.execute("""
                SELECT * FROM tasks 
                WHERE status = 'pending' 
                ORDER BY priority DESC, created_at ASC 
                LIMIT 1
            """)
            task = cursor.fetchone()
            
            if task:
                task_id = task['id']
                cursor.execute("""
                    UPDATE tasks 
                    SET status = 'running', started_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (task_id,))
                conn.commit()
                
                # Return the task as a dict
                return dict(task)
            return None

    def update_task(self, task_id: int, status: TaskStatus, 
                   result: Optional[str] = None, error: Optional[str] = None):
        with sqlite3.connect(self.db_path) as conn:
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

    def get_task_count(self, status: Optional[TaskStatus] = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", (status.value,))
            else:
                cursor.execute("SELECT COUNT(*) FROM tasks")
            return cursor.fetchone()[0]

    def get_tasks(self, limit: int = 100, offset: int = 0, 
                 status: Optional[TaskStatus] = None) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
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
                
            return [dict(row) for row in cursor.fetchall()]

    def cleanup_old_tasks(self, days: int = 7):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM tasks 
                WHERE completed_at IS NOT NULL 
                AND completed_at < datetime('now', ?)
            """, (f'-{days} days',))
            conn.commit()