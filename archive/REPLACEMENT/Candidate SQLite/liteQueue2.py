def _check_table_name(name: str) -> str:
    """
    Check if the table name is valid.
    """

    for char in "[]'`\"":
        if char in name:
            raise ValueError(f"Invalid table name: {name}")
    return name


class LiteQueue:
    def __init__(
        self,
        filename_or_conn: Optional[Union[sqlite3.Connection, str, pathlib.Path]] = None,
        memory: bool = False,
        maxsize: Optional[int] = None,
        queue_name: str = "Queue",
        sqlite_cache_size_bytes: int = 256_000,
        **kwargs,
    ):
        """
        Create a new queue.

        Args:
            - filename_or_conn: str, pathlib.Path, sqlite3.Connection
            - memory: Whether to use an in-memory database or not (default: False)
            - maxsize: Maximum number of messages allowed in the queue (default: None)
            - queue_name: Name of the table that will store the messages (default: "Queue")
            - sqlite_cache_size_bytes: Size for the SQLite cache_size in bytes (default: 256_000 [256MB])
        """
        assert (filename_or_conn is not None and not memory) or (
            filename_or_conn is None and memory
        ), "Either specify a filename_or_conn or pass memory=True"

        assert sqlite_cache_size_bytes > 0
        cache_n = -1 * sqlite_cache_size_bytes

        if memory:
            self.conn = sqlite3.connect(":memory:")
        elif isinstance(filename_or_conn, sqlite3.Connection):
            self.conn = filename_or_conn
        else:
            self.conn = sqlite3.connect(str(filename_or_conn))

        self.queue_name = _check_table_name(queue_name)
        self.maxsize = maxsize

        self.conn.execute(f"PRAGMA cache_size = {cache_n};")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA journal_mode = WAL;")

        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.queue_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message BLOB,
                in_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                lock_time TIMESTAMP,
                done_time TIMESTAMP
            );
            """
        )

        if self.maxsize is not None:
            self.conn.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {self.queue_name}_maxsize
                BEFORE INSERT ON {self.queue_name}
                WHEN (SELECT COUNT(*) FROM {self.queue_name} WHERE done_time IS NULL) >= {self.maxsize}
                BEGIN
                    SELECT RAISE(FAIL, 'Queue is full');
                END;
                """
            )

    # SQLite works better in autocommit mode when using short DML (INSERT /
    # UPDATE / DELETE) statements
    @contextmanager
    def transaction(self, mode="DEFERRED"):
        if mode not in {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}:
            raise ValueError(f"Transaction mode '{mode}' is not valid")
        # We must issue a "BEGIN" explicitly when running in auto-commit mode.
        self.conn.execute(f"BEGIN {mode}")
        try:
            yield
        finally:
            self.conn.commit()

    def put(self, message):
        with self.transaction():
            self.conn.execute(
                f"INSERT INTO {self.queue_name} (message) VALUES (?)",
                (message,)
            )

    def pop(self):
        with self.transaction("IMMEDIATE"):
            cursor = self.conn.cursor()
            cursor.execute(
                f"UPDATE {self.queue_name} SET lock_time = CURRENT_TIMESTAMP WHERE id = (SELECT id FROM {self.queue_name} WHERE lock_time IS NULL AND done_time IS NULL ORDER BY id LIMIT 1) RETURNING id, message"
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return row

    def done(self, message_id):
        with self.transaction():
            self.conn.execute(
                f"UPDATE {self.queue_name} SET done_time = CURRENT_TIMESTAMP WHERE id = ?",
                (message_id,)
            )

    def prune(self):
        with self.transaction():
            self.conn.execute(f"DELETE FROM {self.queue_name} WHERE done_time IS NOT NULL")

    def qsize(self):
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {self.queue_name} WHERE done_time IS NULL")
        return cursor.fetchone()[0]

    def vacuum(self):
        """
        Vacuum the database to remove unused space.

        IMPORTANT: The `VACUUM` step can take some time to finish depending on
        the size of the queue and how many messages have been deleted.
        """
        self.conn.execute("VACUUM;")