# Android-style task queue with ContentProvider pattern
import sqlite3
import json
import threading
from datetime import datetime

class AndroidStyleQueue:
    """Mimics Android's ContentProvider async task handling"""
    
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                _id INTEGER PRIMARY KEY AUTOINCREMENT,
                uri TEXT NOT NULL,
                operation TEXT NOT NULL,
                data TEXT,
                status INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()
    
    def insert(self, uri, operation, data):
        cursor = self.conn.execute(
            "INSERT INTO tasks (uri, operation, data) VALUES (?, ?, ?)",
            (uri, operation, json.dumps(data))
        )
        return cursor.lastrowid
    
    def query_pending(self):
        return self.conn.execute(
            "SELECT * FROM tasks WHERE status = 0 ORDER BY _id LIMIT 1"
        ).fetchone()