#!/usr/bin/env python3
# aios_queue.py — SQLite task queue + worker (compatible with your systemd wrapper)
import os, sys, time, json, sqlite3, argparse, signal, subprocess, threading
from pathlib import Path

DB_PATH_DEFAULT = str(Path(__file__).with_name("aios.db"))
HEARTBEAT_SECS = 5
STALE_SECS = 300  # requeue if no heartbeat in 5 min

def connect(db_path):
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=3000;")
    return conn

def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tasks(
      id INTEGER PRIMARY KEY,
      status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
      priority INTEGER NOT NULL DEFAULT 0,
      run_after INTEGER NOT NULL DEFAULT (strftime('%s','now')),
      attempts INTEGER NOT NULL DEFAULT 0,
      max_attempts INTEGER NOT NULL DEFAULT 3,
      cmd TEXT NOT NULL,
      payload TEXT,
      created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
      claimed_by TEXT,
      claimed_at INTEGER,
      last_heartbeat INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_q ON tasks(status, run_after, priority, created_at);
    CREATE TABLE IF NOT EXISTS runs(
      id INTEGER PRIMARY KEY,
      task_id INTEGER NOT NULL,
      attempt INTEGER NOT NULL,
      worker TEXT,
      started_at INTEGER NOT NULL,
      ended_at INTEGER,
      exit_code INTEGER,
      stdout TEXT,
      stderr TEXT
    );
    CREATE TABLE IF NOT EXISTS events(
      ts INTEGER NOT NULL DEFAULT (strftime('%s','now')),
      type TEXT NOT NULL,
      task_id INTEGER,
      meta TEXT
    );
    """)
    conn.execute("INSERT INTO events(type,meta) VALUES('init','{}');")

def enqueue(conn, cmd, priority=0, run_after=None, payload=None, max_attempts=3):
    conn.execute("BEGIN;")
    try:
        ra = run_after if run_after is not None else int(time.time())
        conn.execute("""INSERT INTO tasks(status,priority,run_after,cmd,payload,max_attempts)
                        VALUES('queued',?,?,?,?,?)""",
                     (priority, ra, cmd, json.dumps(payload) if payload else None, max_attempts))
        conn.execute("INSERT INTO events(type,meta) VALUES('enqueue',json(?));",
                     (json.dumps({"cmd":cmd,"priority":priority,"run_after":ra}),))
        conn.execute("COMMIT;")
    except:
        conn.execute("ROLLBACK;"); raise

def next_due(conn):
    row = conn.execute("SELECT MIN(run_after) FROM tasks WHERE status='queued'").fetchone()
    return row[0] if row and row[0] else None

def requeue_stale(conn):
    cutoff = int(time.time()) - STALE_SECS
    cur = conn.execute("""UPDATE tasks
                          SET status='queued', claimed_by=NULL, claimed_at=NULL, last_heartbeat=NULL
                          WHERE status='running' AND (last_heartbeat IS NULL OR last_heartbeat<?);""",
                       (cutoff,))
    n = cur.rowcount or 0
    if n:
        conn.execute("INSERT INTO events(type,meta) VALUES('requeue_stale',json(?));",
                     (json.dumps({"count":n}),))

def atomic_claim(conn, worker):
    """Portable 2-step claim inside a txn (works without RETURNING)."""
    conn.execute("BEGIN;")
    try:
        row = conn.execute("""
            SELECT id FROM tasks
            WHERE status='queued' AND run_after<=? 
            ORDER BY priority DESC, created_at ASC LIMIT 1;""",
            (int(time.time()),)).fetchone()
        if not row:
            conn.execute("COMMIT;"); return None
        task_id = row[0]
        cur = conn.execute("""UPDATE tasks
                              SET status='running', claimed_by=?, claimed_at=strftime('%s','now'),
                                  attempts=attempts+1, last_heartbeat=strftime('%s','now')
                              WHERE id=? AND status='queued';""",
                           (worker, task_id))
        if cur.rowcount != 1:
            conn.execute("ROLLBACK;"); return None
        task = conn.execute("SELECT id,cmd,attempts,max_attempts,payload FROM tasks WHERE id=?;", (task_id,)).fetchone()
        conn.execute("INSERT INTO runs(task_id,attempt,worker,started_at) VALUES(?,?,?,strftime('%s','now'));",
                     (task_id, task[2], worker))
        conn.execute("INSERT INTO events(type,task_id,meta) VALUES('claim',?,json(?));",
                     (task_id, json.dumps({"worker":worker})))
        conn.execute("COMMIT;")
        return {"id":task[0], "cmd":task[1], "attempts":task[2], "max_attempts":task[3], "payload":task[4]}
    except Exception:
        conn.execute("ROLLBACK;"); raise

def heartbeat_loop(conn, worker, task_id, stop_evt):
    while not stop_evt.wait(HEARTBEAT_SECS):
        conn.execute("UPDATE tasks SET last_heartbeat=strftime('%s','now') WHERE id=?", (task_id,))

def complete(conn, task_id, success, exit_code, out_txt, err_txt):
    status = 'succeeded' if success else 'failed'
    conn.execute("BEGIN;")
    try:
        conn.execute("UPDATE tasks SET status=?, last_heartbeat=strftime('%s','now') WHERE id=?;", (status, task_id))
        conn.execute("""UPDATE runs SET ended_at=strftime('%s','now'), exit_code=?, stdout=?, stderr=?
                        WHERE task_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1;""",
                     (exit_code, out_txt, err_txt, task_id))
        conn.execute("INSERT INTO events(type,task_id,meta) VALUES('complete',?,json(?));",
                     (task_id, json.dumps({"status":status,"exit_code":exit_code})))
        conn.execute("COMMIT;")
    except:
        conn.execute("ROLLBACK;"); raise

def maybe_backoff_requeue(conn, task_id, attempts, max_attempts):
    if attempts < max_attempts:
        # Exponential backoff: now + 2^(attempts-1) seconds, capped minimal design
        delay = min(3600, 2 ** max(0, attempts-1))
        conn.execute("""UPDATE tasks SET status='queued', run_after=strftime('%s','now')+?
                        WHERE id=?;""", (delay, task_id))
        conn.execute("INSERT INTO events(type,task_id,meta) VALUES('retry',?,json(?));",
                     (task_id, json.dumps({"delay":delay,"attempts":attempts})))

def run_cmd(cmd):
    # Execute command via shell for parity with your orchestrator; could switch to argv for safety.
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=os.setsid)
    out, err = p.communicate()
    return p.returncode, out[-65536:], err[-65536:]  # cap logs

def worker_loop(db_path, name):
    conn = connect(db_path); init_db(conn)
    print(f"[worker {name}] started; db={db_path}")
    while True:
        requeue_stale(conn)
        task = atomic_claim(conn, name)
        if not task:
            nd = next_due(conn)
            sleep_s = max(0.25, (nd - int(time.time())) if nd else 0.5)
            time.sleep(min(2.0, sleep_s)); continue
        stop_evt = threading.Event()
        hb_thr = threading.Thread(target=heartbeat_loop, args=(conn, name, task["id"], stop_evt), daemon=True)
        hb_thr.start()
        rc, out, err = run_cmd(task["cmd"])
        stop_evt.set(); hb_thr.join(timeout=1)
        success = (rc == 0)
        complete(conn, task["id"], success, rc, out, err)
        if not success:
            maybe_backoff_requeue(conn, task["id"], task["attempts"], task["max_attempts"])

def cli():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--db", default=DB_PATH_DEFAULT)

    p_enqueue = sub.add_parser("enqueue")
    p_enqueue.add_argument("--db", default=DB_PATH_DEFAULT)
    p_enqueue.add_argument("--cmd", required=True)
    p_enqueue.add_argument("--priority", type=int, default=0)
    p_enqueue.add_argument("--run_after", type=int)
    p_enqueue.add_argument("--payload")

    p_worker = sub.add_parser("worker")
    p_worker.add_argument("--db", default=DB_PATH_DEFAULT)
    p_worker.add_argument("--name", default=os.uname().nodename)

    p_dump = sub.add_parser("status")
    p_dump.add_argument("--db", default=DB_PATH_DEFAULT)

    args = ap.parse_args()
    if args.cmd == "init":
        conn = connect(args.db); init_db(conn); print("DB ready:", args.db)
    elif args.cmd == "enqueue":
        conn = connect(args.db); init_db(conn)
        payload = json.loads(args.payload) if args.payload else None
        enqueue(conn, args.cmd, args.priority, args.run_after, payload)
        print("enqueued")
    elif args.cmd == "worker":
        worker_loop(args.db, args.name)
    elif args.cmd == "status":
        conn = connect(args.db)
        rows = conn.execute("""SELECT status,COUNT(*)
                               FROM tasks GROUP BY status;""").fetchall()
        print(dict(rows))

if __name__ == "__main__":
    cli()
