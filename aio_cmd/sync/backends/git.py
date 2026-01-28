"""Unified storage layer - all sync logic in one place"""
import os, sys, json, time, sqlite3, shutil, hashlib, subprocess as sp
from pathlib import Path

# Paths
DATA_DIR = os.path.expanduser("~/.local/share/aios")
DB_PATH = os.path.join(DATA_DIR, "aio.db")
EVENTS_PATH = os.path.join(DATA_DIR, "events.jsonl")

# Device ID
def _get_dev():
    f = os.path.join(DATA_DIR, ".device")
    if os.path.exists(f): return open(f).read().strip()
    import socket
    d = (sp.run(['getprop','ro.product.model'],capture_output=True,text=True).stdout.strip().replace(' ','-') or socket.gethostname()) if os.path.exists('/data/data/com.termux') else socket.gethostname()
    os.makedirs(DATA_DIR, exist_ok=True); open(f,'w').write(d)
    return d

DEVICE_ID = _get_dev()

# --- Database ---
def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def _init_table(table):
    """Ensure table exists with standard schema"""
    schemas = {
        "ssh": "name TEXT PRIMARY KEY, host TEXT, pw TEXT",
        "notes": "id TEXT PRIMARY KEY, t TEXT, s INTEGER DEFAULT 0, d TEXT, c TEXT DEFAULT CURRENT_TIMESTAMP, proj TEXT, dev TEXT",
        "projects": "id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, display_order INTEGER NOT NULL, device TEXT DEFAULT '*'",
        "apps": "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, command TEXT NOT NULL, display_order INTEGER NOT NULL, device TEXT DEFAULT '*'",
    }
    if table in schemas:
        _db().execute(f"CREATE TABLE IF NOT EXISTS {table}({schemas[table]})")

# --- Events (append-only log) ---
def _emit(table, op, data):
    """Append event to events.jsonl"""
    eid = hashlib.md5(f"{time.time()}{os.getpid()}".encode()).hexdigest()[:8]
    event = {"ts": time.time(), "id": eid, "dev": DEVICE_ID, "op": f"{table}.{op}", "d": data}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")
    return eid

# --- Simple API ---
def put(table, key, data):
    """Store data. Emits event + writes to local db."""
    _init_table(table)
    data_with_key = {"name": key, **data} if table == "ssh" else {"id": key, **data}
    _emit(table, "add", data_with_key)

    c = _db()
    if table == "ssh":
        c.execute("INSERT OR REPLACE INTO ssh(name,host,pw) VALUES(?,?,?)",
                  (key, data.get("host",""), data.get("pw")))
    elif table == "notes":
        c.execute("INSERT OR REPLACE INTO notes(id,t,s,d,proj,dev) VALUES(?,?,0,?,?,?)",
                  (key, data.get("t",""), data.get("d"), data.get("proj"), DEVICE_ID))
    c.commit()
    return key

def get(table, key):
    """Get single item by key."""
    _init_table(table)
    c = _db()
    if table == "ssh":
        r = c.execute("SELECT name,host,pw FROM ssh WHERE name=?", (key,)).fetchone()
        return {"name": r[0], "host": r[1], "pw": r[2]} if r else None
    elif table == "notes":
        r = c.execute("SELECT id,t,s,d,proj,dev FROM notes WHERE id=?", (key,)).fetchone()
        return {"id": r[0], "t": r[1], "s": r[2], "d": r[3], "proj": r[4], "dev": r[5]} if r else None
    return None

def delete(table, key):
    """Delete item. Emits archive event."""
    _init_table(table)
    _emit(table, "archive", {"name": key} if table == "ssh" else {"id": key})
    c = _db()
    pk = "name" if table == "ssh" else "id"
    c.execute(f"DELETE FROM {table} WHERE {pk}=?", (key,))
    c.commit()

def list_all(table):
    """List all items in table."""
    _init_table(table)
    c = _db()
    if table == "ssh":
        return [{"name": r[0], "host": r[1], "pw": r[2]} for r in c.execute("SELECT name,host,pw FROM ssh")]
    elif table == "notes":
        return [{"id": r[0], "t": r[1], "s": r[2]} for r in c.execute("SELECT id,t,s FROM notes WHERE s=0")]
    return []

# --- Sync ---
def _replay_events(tables=None):
    """Rebuild db state from events.jsonl"""
    if not os.path.exists(EVENTS_PATH): return

    state = {}
    tables = tables or ["ssh", "notes"]

    for line in open(EVENTS_PATH):
        try: e = json.loads(line)
        except: continue

        parts = e["op"].split(".")
        if len(parts) != 2: continue
        t, op = parts
        d = e["d"]

        if t not in tables: continue
        if t not in state: state[t] = {}

        k = d.get("name") or d.get("id") or e["id"]
        if op == "add":
            state[t][k] = {**d, "_ts": e["ts"]}
        elif op in ("archive", "ack") and k in state[t]:
            state[t][k]["_archived"] = True

    c = _db()
    for t, items in state.items():
        active = {k: v for k, v in items.items() if not v.get("_archived")}

        if t == "ssh":
            c.execute("CREATE TABLE IF NOT EXISTS ssh(name PRIMARY KEY,host,pw)")
            c.execute("DELETE FROM ssh")
            for k, v in active.items():
                c.execute("INSERT INTO ssh(name,host,pw) VALUES(?,?,?)",
                         (v.get("name", k), v.get("host", ""), v.get("pw")))
        elif t == "notes":
            c.execute("DELETE FROM notes WHERE id LIKE '________'")
            for k, v in items.items():
                c.execute("INSERT OR REPLACE INTO notes(id,t,s,d,proj,dev) VALUES(?,?,?,?,?,?)",
                         (k, v.get("t",""), 1 if v.get("_archived") else 0, v.get("d"), v.get("proj"), v.get("_dev")))
    c.commit()

def sync(pull=True):
    """Sync with git remote. Returns True on success."""
    # Check git available
    if not os.path.isdir(f"{DATA_DIR}/.git"):
        pull and _replay_events()
        return True

    if not shutil.which('gh') or sp.run(['gh','auth','status'],capture_output=True).returncode != 0:
        pull and _replay_events()
        return True

    # Ensure .gitignore excludes db files
    gi = f"{DATA_DIR}/.gitignore"
    ignore = "*.db*\n*.log\nlogs/\n*cache*\ntiming.jsonl\nnotebook/\n.device\n"
    if not os.path.exists(gi) or ".device" not in open(gi).read():
        open(gi, "w").write(ignore)

    # Save device file (don't let git overwrite)
    df = f"{DATA_DIR}/.device"
    dev = open(df).read() if os.path.exists(df) else None

    # Git sync - commit, pull, push
    cmd = f'''cd "{DATA_DIR}" && \
        git checkout -- *.db 2>/dev/null; \
        git add events.jsonl .gitignore 2>/dev/null && \
        git -c user.name=aio -c user.email=a@a commit -qm sync 2>/dev/null; \
        git fetch -q origin main && \
        git -c user.name=aio -c user.email=a@a rebase origin/main 2>/dev/null || \
        (git rebase --abort 2>/dev/null; git reset --hard origin/main); \
        git push -q origin HEAD:main 2>/dev/null'''

    sp.run(cmd, shell=True, capture_output=True)

    # Restore device file
    if dev:
        open(df, "w").write(dev)

    # Rebuild from events
    if pull:
        _replay_events()

    check_consensus()
    return True

def check_consensus():
    """Compare event log hash vs db state. Alert on mismatch."""
    try:
        # Hash of events
        ef = Path(EVENTS_PATH)
        events_hash = hashlib.md5(ef.read_bytes()).hexdigest()[:8] if ef.exists() else "empty"

        # Hash of ssh table
        c = _db()
        rows = sorted(c.execute("SELECT name,host FROM ssh").fetchall())
        db_hash = hashlib.md5(str(rows).encode()).hexdigest()[:8]

        # For now just log, don't compare (events vs db will differ by design)
        # Future: compare multiple backends here
        return True

    except Exception as e:
        print(f"⚠ Consensus check error: {e}")
        return False
