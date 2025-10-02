import json, sqlite3, pathlib

# Database connection
db_path = pathlib.Path(__file__).parent.parent / "data/aios.db"
d = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)

# Set pragmas for performance
[d.execute(p) for p in ["PRAGMA synchronous=0", "PRAGMA journal_mode=MEMORY"]]

# Create tables
tables = [
    """CREATE TABLE IF NOT EXISTS kv(
        k TEXT PRIMARY KEY,
        v TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY,
        name TEXT,
        status TEXT,
        output TEXT,
        created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY,
        content TEXT,
        timestamp TEXT,
        source TEXT,
        priority INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS worktrees(
        id INTEGER PRIMARY KEY,
        repo TEXT,
        branch TEXT,
        path TEXT,
        job_id INTEGER,
        model TEXT,
        task TEXT,
        status TEXT,
        output TEXT,
        created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY,
        target TEXT,
        data TEXT,
        created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
]
d.executescript(";".join(tables))

# Database functions
read = lambda n: json.loads(d.execute("SELECT v FROM kv WHERE k=?", (n,)).fetchone()[0])
write = lambda n, x: (d.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (n, json.dumps(x, indent=2))), x)[1]
query = lambda _, s, p=(): d.execute(s, p).fetchall()
execute = lambda _, s, p=(): d.execute(s, p)
