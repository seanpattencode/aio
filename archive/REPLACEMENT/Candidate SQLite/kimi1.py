# litequeue/__init__.py  –  Ricardo Ander-Egg, MIT
# https://github.com/litements/litequeue/blob/main/litequeue/__init__.py
import sqlite3
import json
import time
import uuid
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, List


class MessageStatus(IntEnum):
    READY = 0
    LOCKED = 1
    DONE = 2


@dataclass
class Message:
    data: str
    message_id: uuid.UUID
    status: MessageStatus
    in_time: int
    lock_time: Optional[int] = None
    done_time: Optional[int] = None


class LiteQueue:
    """
    Very small queue on top of SQLite.
    """
    def __init__(self, filename_or_conn=":memory:", queue_name="queue"):
        if isinstance(filename_or_conn, sqlite3.Connection):
            self.conn = filename_or_conn
        else:
            self.conn = sqlite3.connect(filename_or_conn, check_same_thread=False)
        self.queue_name = queue_name
        self._create_table()

    def _create_table(self):
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.queue_name}(
                message_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                status INTEGER NOT NULL,
                in_time INTEGER NOT NULL,
                lock_time INTEGER,
                done_time INTEGER
            ) WITHOUT ROWID;
            """
        )
        self.conn.commit()

    def put(self, data: str) -> uuid.UUID:
        mid = uuid.uuid4()
        now = time.time_ns()
        self.conn.execute(
            f"INSERT INTO {self.queue_name} VALUES (?,?,?,?,?,?)",
            (str(mid), data, MessageStatus.READY, now, None, None),
        )
        self.conn.commit()
        return mid

    def pop(self) -> Optional[Message]:
        with self.conn:
            cur = self.conn.execute(
                f"""
                SELECT * FROM {self.queue_name}
                WHERE status=?
                ORDER BY in_time
                LIMIT 1
                """,
                (MessageStatus.READY,),
            )
            row = cur.fetchone()
            if not row:
                return None
            mid = row[0]
            now = time.time_ns()
            self.conn.execute(
                f"UPDATE {self.queue_name} SET status=?, lock_time=? WHERE message_id=?",
                (MessageStatus.LOCKED, now, mid),
            )
            return Message(*row)

    def done(self, message_id: uuid.UUID):
        now = time.time_ns()
        with self.conn:
            self.conn.execute(
                f"UPDATE {self.queue_name} SET status=?, done_time=? WHERE message_id=?",
                (MessageStatus.DONE, now, str(message_id)),
            )

    def get(self, message_id: uuid.UUID) -> Optional[Message]:
        cur = self.conn.execute(
            f"SELECT * FROM {self.queue_name} WHERE message_id=?", (str(message_id),)
        )
        row = cur.fetchone()
        if row:
            return Message(*row)
        return None

    def qsize(self) -> int:
        cur = self.conn.execute(
            f"SELECT COUNT(*) FROM {self.queue_name} WHERE status=?",
            (MessageStatus.READY,),
        )
        return cur.fetchone()[0]

    def prune(self) -> int:
        with self.conn:
            cur = self.conn.execute(
                f"DELETE FROM {self.queue_name} WHERE status=?", (MessageStatus.DONE,)
            )
            return cur.rowcount