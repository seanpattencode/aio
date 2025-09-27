import json, sqlite3
db_path = __file__[:-24] + ".aios"
d = sqlite3.connect(__file__[:-14] + "aios.db", isolation_level=None, check_same_thread=False)
d.execute("PRAGMA synchronous=0")
d.execute("PRAGMA journal_mode=MEMORY")
d.executescript("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY,v TEXT);CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,name TEXT,status TEXT,output TEXT,created TIMESTAMP DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,content TEXT,timestamp TEXT,source TEXT,priority INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS worktrees(id INTEGER PRIMARY KEY,repo TEXT,branch TEXT,path TEXT,job_id INTEGER,model TEXT,task TEXT,status TEXT,output TEXT,created TIMESTAMP DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,target TEXT,data TEXT,created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
def read(n): r = d.execute("SELECT v FROM kv WHERE k=?", (n,)).fetchone(); return json.loads(r[0]) if r else None
def write(n, x): d.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (n, json.dumps(x, indent=2))); return x
def query(_, s, p=()): return d.execute(s, p).fetchall()
def execute(_, s, p=()): d.execute(s, p)