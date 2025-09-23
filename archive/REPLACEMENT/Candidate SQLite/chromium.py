# Chrome-style sequential task runner
import sqlite3
import time
import json

class ChromeTaskQueue:
    """Chrome's approach: single writer, sequential processing"""
    
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS task_queue (
                id INTEGER PRIMARY KEY,
                task_name TEXT NOT NULL,
                params TEXT,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_ns INTEGER,
                started_ns INTEGER,
                completed_ns INTEGER
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON task_queue(status)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON task_queue(priority DESC)")
        self.conn.commit()
    
    def post_task(self, task_name, params, priority=0):
        ns = time.time_ns()
        self.conn.execute(
            "INSERT INTO task_queue (task_name, params, priority, created_ns) VALUES (?, ?, ?, ?)",
            (task_name, json.dumps(params), priority, ns)
        )
        self.conn.commit()