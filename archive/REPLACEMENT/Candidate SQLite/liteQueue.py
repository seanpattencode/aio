# Simplified version of the popular litequeue library
import sqlite3
import json
import time
import uuid
from contextlib import contextmanager
from enum import Enum

class MessageStatus(Enum):
    READY = 0
    LOCKED = 1  
    DONE = 2
    FAILED = 3

class LiteQueue:
    def __init__(self, db_path, table_name="queue"):
        self.conn = sqlite3.connect(db_path)
        self.table = table_name
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                message_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                status INTEGER DEFAULT 0,
                in_time INTEGER NOT NULL,
                lock_time INTEGER,
                done_time INTEGER
            )
        """)
        self.conn.commit()
    
    def put(self, data):
        message_id = str(uuid.uuid4())
        in_time = time.time_ns()
        self.conn.execute(
            f"INSERT INTO {self.table} (message_id, data, status, in_time) VALUES (?, ?, ?, ?)",
            (message_id, data, MessageStatus.READY.value, in_time)
        )
        self.conn.commit()
        return message_id
    
    def pop(self):
        with self.transaction("IMMEDIATE"):
            row = self.conn.execute(
                f"SELECT * FROM {self.table} WHERE status = ? ORDER BY in_time LIMIT 1",
                (MessageStatus.READY.value,)
            ).fetchone()
            
            if row:
                message_id = row[0]
                lock_time = time.time_ns()
                self.conn.execute(
                    f"UPDATE {self.table} SET status = ?, lock_time = ? WHERE message_id = ?",
                    (MessageStatus.LOCKED.value, lock_time, message_id)
                )
                return row
        return None
    
    @contextmanager
    def transaction(self, mode="DEFERRED"):
        self.conn.execute(f"BEGIN {mode}")
        try:
            yield
        except Exception as e:
            self.conn.rollback()
            raise e
        else:
            self.conn.commit()