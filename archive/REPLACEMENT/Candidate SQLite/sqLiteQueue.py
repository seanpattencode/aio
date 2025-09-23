"""A thread-safe sqlite3 based persistent queue in Python."""
import logging
import sqlite3
import time as _time
import threading
from typing import Any
from persistqueue import sqlbase

sqlite3.enable_callback_tracebacks(True)
log = logging.getLogger(__name__)


class SQLiteQueue(sqlbase.SQLiteBase):
    """SQLite3 based FIFO queue."""
    _TABLE_NAME = 'queue'
    _KEY_COLUMN = '_id'  # the name of the key column, used in DB CRUD
    # SQL to create a table
    _SQL_CREATE = (
        'CREATE TABLE IF NOT EXISTS {table_name} ('
        '{key_column} INTEGER PRIMARY KEY AUTOINCREMENT, '
        'data BLOB, timestamp FLOAT)'
    )
    # SQL to insert a record
    _SQL_INSERT = 'INSERT INTO {table_name} (data, timestamp) VALUES (?, ?)'
    # SQL to select a record
    _SQL_SELECT_ID = (
        'SELECT {key_column}, data, timestamp FROM {table_name} WHERE {key_column} = ?'
    )
    _SQL_SELECT = (
        'SELECT {key_column}, data FROM {table_name} '
        'ORDER BY {key_column} LIMIT 1'
    )
    # SQL to select with ID > some_id
    _SQL_SELECT_WHERE_GT = (
        'SELECT {key_column}, data FROM {table_name} '
        'WHERE {key_column} > ? '
        'ORDER BY {key_column} LIMIT 1'
    )
    _SQL_UPDATE = 'UPDATE {table_name} SET data = ? WHERE {key_column} = ?'
    # SQL to delete a record
    _SQL_DELETE_ID = 'DELETE FROM {table_name} WHERE {key_column} = ?'
    # SQL to delete a record with id < some_id
    _SQL_DELETE_LT = 'DELETE FROM {table_name} WHERE {key_column} < ?'
    _SQL_DELETE_LTE = 'DELETE FROM {table_name} WHERE {key_column} <= ?'

    def _put(self, item: Any):
        self._insert_into(item, _time.time())

    def _get(self) -> Any:
        row = self._select_op()
        if not row:
            raise sqlbase.Empty
        self._delete_id(row[0])
        return row[1]


FIFOSQLiteQueue = SQLiteQueue


class FILOSQLiteQueue(SQLiteQueue):
    """SQLite3 based FILO queue."""
    _TABLE_NAME = 'filo_queue'
    # SQL to select a record
    _SQL_SELECT = (
        'SELECT {key_column}, data FROM {table_name} '
        'ORDER BY {key_column} DESC LIMIT 1'
    )

# From sqlbase.py (required base):
import os
import sqlite3
from typing import Any, Callable, List, Optional, Union
from .exceptions import Full
from .serializers import get_serializer, pickle_serializer

class SQLBase:
    def __init__(self):
        self._serializer = pickle_serializer
        self._getter = None
        self._putter = None

    def put(self, item: Any):
        self._put(self._serializer.dumps(item))

    def get(self) -> Any:
        data = self._get()
        return self._serializer.loads(data)

    def _init(self) -> None:
        pass

class SQLiteBase(SQLBase):
    _TABLE_NAME = 'base'  # DB table name
    _KEY_COLUMN = ''  # the name of the key column, used in DB CRUD
    _SQL_CREATE = ''  # SQL to create a table
    _SQL_UPDATE = ''  # SQL to update a record
    _SQL_INSERT = ''  # SQL to insert a record
    _SQL_SELECT = ''  # SQL to select a record
    _SQL_SELECT_ID = ''  # SQL to select a record with id
    _SQL_SELECT_WHERE_GT = ''  # SQL to select a record with id > some_id
    _SQL_DELETE_ID = ''  # SQL to delete a record
    _SQL_DELETE_LT = ''  # SQL to delete a record with id < some_id
    _SQL_DELETE_LTE = ''  # SQL to delete a record with id <= some_id
    _SQL_COUNT = ''  # SQL to count # of records

    def __init__(
        self,
        path: str,
        name: str = "queue",
        multithreading: bool = False,
        timeout: float = 10.0,
        auto_commit: bool = True,
        serializer: Optional[Union[str, Callable]] = None,
        db_file_name: Optional[str] = None,
    ):
        super().__init__()
        self.path = path
        self.name = name
        self.timeout = timeout
        self.multithreading = multithreading
        self.auto_commit = auto_commit
        if serializer:
            self._serializer = get_serializer(serializer)
        self.db_file_name = db_file_name or "data.db"
        self._init()

    def _init(self) -> None:
        """Initialize the tables in DB."""
        if self.path == ':memory:':
            log.debug("Initializing SQLite3 Queue in memory.")
        elif not os.path.exists(self.path):
            os.makedirs(self.path)
            log.debug(
                'Initializing SQLite3 Queue with path {}'.format(self.path)
            )
        self._conn = self._new_db_connection(
            self.path, self.multithreading, self.timeout
        )
        self._getter = self._conn
        self._putter = self._conn
        if self.multithreading:
            self._getter = self._new_db_connection(
                self.path, self.multithreading, self.timeout
            )
            self._putter = self._new_db_connection(
                self.path, self.multithreading, self.timeout
            )
        self._table_name = self._TABLE_NAME if not self.name else f"{self.name}_{self._TABLE_NAME}"
        self._key_column = self._KEY_COLUMN
        self._create_table()

    def _new_db_connection(self, path: str, multithreading: bool, timeout: float) -> sqlite3.Connection:
        db_path = path if path == ':memory:' else os.path.join(path, self.db_file_name)
        conn = sqlite3.connect(db_path, timeout=timeout, check_same_thread=not multithreading)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _create_table(self):
        self._conn.execute(self._SQL_CREATE.format(table_name=self._table_name, key_column=self._key_column))

# Additional ack version from sqlackqueue.py (extension for ack):
class AckStatus:
    inited = '0'
    ready = '1'
    unack = '2'
    acked = '5'
    ack_failed = '9'

class SQLiteAckQueue(SQLiteBase):
    """SQLite3 based FIFO queue with ack support."""
    _TABLE_NAME = 'ack_queue'
    _KEY_COLUMN = '_id'  # the name of the key column, used in DB CRUD
    # SQL to create a table
    _SQL_CREATE = (
        'CREATE TABLE IF NOT EXISTS {table_name} ('
        '{key_column} INTEGER PRIMARY KEY AUTOINCREMENT, '
        'data BLOB, timestamp FLOAT, status INTEGER, ack_failed_reason BLOB)'
    )
    # SQL to insert a record
    _SQL_INSERT = 'INSERT INTO {table_name} (data, timestamp, status) VALUES (?, ?, ?)'
    # SQL to select a record
    _SQL_SELECT = (
        'SELECT {key_column}, data FROM {table_name} '
        'WHERE status = ? '
        'ORDER BY {key_column} LIMIT 1'
    )
    # SQL to select a record with id
    _SQL_SELECT_ID = (
        'SELECT {key_column}, data, timestamp FROM {table_name} WHERE {key_column} = ?'
    )
    # SQL to select a record with status < unack
    _SQL_SELECT_READY = (
        'SELECT {key_column}, data FROM {table_name} '
        'WHERE status < ? '
        'ORDER BY {key_column} LIMIT 1'
    )
    # SQL to count # of records with status < unack
    _SQL_COUNT_READY = (
        'SELECT COUNT(*) FROM {table_name} WHERE status < ?'
    )
    _SQL_UPDATE_STATUS = (
        'UPDATE {table_name} SET status = ? WHERE {key_column} = ?'
    )
    _SQL_SELECT_WHERE = (
        'SELECT {key_column}, data, timestamp FROM {table_name}'
        ' WHERE {key_column} > {rowid} AND status < %s AND'
        ' {column} {op} ? ORDER BY {key_column} ASC'
        ' LIMIT 1 ' % AckStatus.unack
    )
    _SQL_UPDATE = 'UPDATE {table_name} SET data = ? WHERE {key_column} = ?'

    def __init__(self, path: str, auto_resume: bool = True, **kwargs):
        super().__init__(path, **kwargs)
        self.auto_commit = True  # Forced for ack
        self._unack_cache = {}
        if auto_resume:
            self.resume_unack_tasks()

    def put(self, item: Any, **kwargs):
        obj = self._serializer.dumps(item)
        self._insert_into(obj, _time.time(), AckStatus.ready)

    def get(self) -> Any:
        row = self._select_ready()
        if not row:
            raise Empty
        self._update_status(row[0], AckStatus.unack)
        self._unack_cache[row[0]] = row[1]
        return self._serializer.loads(row[1])

    def ack(self, item: Any):
        for k, v in self._unack_cache.items():
            if v == self._serializer.dumps(item):
                self._update_status(k, AckStatus.acked)
                del self._unack_cache[k]
                break

    def ack_failed(self, item: Any, reason: str = ''):
        for k, v in self._unack_cache.items():
            if v == self._serializer.dumps(item):
                self._update_status(k, AckStatus.ack_failed)
                self._update_ack_failed_reason(k, reason)
                del self._unack_cache[k]
                break

    def resume_unack_tasks(self):
        rows = self._select_unack()
        for row in rows:
            self._update_status(row[0], AckStatus.ready)