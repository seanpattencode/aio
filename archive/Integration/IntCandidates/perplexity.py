#!/usr/bin/env python3
"""
Unified Job Orchestration + Management System
- SQLite-backed job store
- Dependencies, priorities, retry, scheduling
- Optional systemd transient units for managed jobs (if available)
- Clean process control; thread-safe
"""
import argparse, json, os, sys, time, sqlite3, threading, subprocess, shlex
from pathlib import Path

# ==== GLOBAL CONSTANTS ====
DB_PATH = os.environ.get("JOB_DB", str(Path.home() / ".job_tasks.db"))
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA busy_timeout=5000"
]

# ==== DATABASE LAYER ====
class DB:
    def __init__(self, db_path=DB_PATH):
        self.lock = threading.RLock()
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        for p in PRAGMAS: self.conn.execute(p)
        self._init_schema()
    def _init_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(
            id INTEGER PRIMARY KEY,
            name TEXT,
            cmd TEXT,
            args TEXT,
            env TEXT,
            priority INTEGER DEFAULT 0,
            status TEXT DEFAULT 'queued',
            schedule TEXT,
            at INTEGER DEFAULT (strftime('%s','now')*1000), -- epoch ms
            worker TEXT,
            result TEXT,
            error TEXT,
            dep TEXT,
            retry INTEGER DEFAULT 0,
            created_at INTEGER DEFAULT (strftime('%s','now')*1000),
            started_at INTEGER,
            ended_at INTEGER,
            rtprio INTEGER,
            nice INTEGER,
            slice TEXT,
            cpu_weight INTEGER,
            mem_max_mb INTEGER,
            unit TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sched ON jobs(status,priority DESC,at,id);
        """)
    def add_job(self, **kw):
        with self.lock:
            dep = json.dumps(kw.get("dep")) if kw.get("dep") else None
            now = int(time.time()*1000)
            r = self.conn.execute("""
            INSERT INTO jobs (name,cmd,args,env,priority,schedule,at,dep,rtprio,nice,slice,cpu_weight,mem_max_mb,created_at) 
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (kw.get("name"), kw.get("cmd"), json.dumps(kw.get("args") or []), json.dumps(kw.get("env") or {}),
                  kw.get("priority",0), kw.get("schedule"), kw.get("at", now), dep, kw.get("rtprio"),
                  kw.get("nice"), kw.get("slice"), kw.get("cpu_weight"), kw.get("mem_max_mb"), now))
            return r.lastrowid
    def list_jobs(self):
        with self.lock:
            return self.conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    def pop_job(self, worker):
        with self.lock:
            now = int(time.time() * 1000)
            row = self.conn.execute("""
                SELECT * FROM jobs
                WHERE status='queued' AND at<=?
                AND (dep IS NULL OR NOT EXISTS (
                    SELECT 1 FROM json_each(jobs.dep) d
                    JOIN jobs AS jb ON jb.id=d.value WHERE jb.status!='done'))
                ORDER BY priority DESC, at, id LIMIT 1
            """, (now,)).fetchone()
            if not row: return None
            r = self.conn.execute("""
                UPDATE jobs SET status='running', worker=?, started_at=?
                WHERE id=? AND status='queued'
                RETURNING id, name, cmd, args, env
            """, (worker, now, row['id'])).fetchone()
            return dict(r) if r else None
    def complete_job(self, job_id, ok=True, result=None, error=None, worker=None):
        with self.lock:
            now = int(time.time()*1000)
            st = self.conn.execute("SELECT started_at, created_at, retry FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not st: return
            if ok:
                self.conn.execute("""
                    UPDATE jobs SET status='done', ended_at=?, result=?, worker=NULL WHERE id=?
                """, (now, json.dumps(result) if result else None, job_id))
            elif st['retry'] < 3:
                delay = 1000 * (2 ** st['retry'])
                self.conn.execute("""
                    UPDATE jobs SET status='queued', at=?, retry=retry+1, error=?, worker=NULL WHERE id=?
                """, (now + delay, error, job_id))
            else:
                self.conn.execute("""
                    UPDATE jobs SET status='failed', ended_at=?, error=?, worker=NULL WHERE id=?
                """, (now, error, job_id))
    def cleanup_jobs(self, days=7):
        threshold = int(time.time()*1000) - days*86400000
        with self.lock:
            delcount = self.conn.execute(
                "DELETE FROM jobs WHERE status IN ('done','failed') AND ended_at < ?", (threshold,)).rowcount
            return delcount
    def update_status(self, job_id, status, unit=None):
        with self.lock:
            self.conn.execute("UPDATE jobs SET status=?, unit=? WHERE id=?", (status, unit, job_id))
    def get_job(self, job_id):
        with self.lock:
            return self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    def get_job_by_name(self, name):
        with self.lock:
            return self.conn.execute("SELECT * FROM jobs WHERE name=?", (name,)).fetchone()
    def update_unit(self, name, unit, status):
        with self.lock:
            self.conn.execute("UPDATE jobs SET unit=?, status=? WHERE name=?", (unit, status, name))

# ==== SYSTEMD LAYER (optional) ====
def systemd_run_args(job):
    # Generates args for systemd-run
    props = [
        "--property=StandardOutput=journal",
        "--property=StandardError=journal",
        "--property=KillMode=control-group"
    ]
    if job["rtprio"]: props += [f"--property=CPUSchedulingPolicy=rr", f"--property=CPUSchedulingPriority={job['rtprio']}"]
    if job["nice"]: props += [f"--property=Nice={job['nice']}"]
    if job["slice"]: props += [f"--slice={job['slice']}"]
    if job["cpu_weight"]: props += [f"--property=CPUWeight={job['cpu_weight']}"]
    if job["mem_max_mb"]: props += [f"--property=MemoryMax={job['mem_max_mb']}M"]
    env = []
    if job["env"]:
        try:
            for k,v in json.loads(job["env"]).items(): env += ["--setenv", f"{k}={v}"]
        except: pass
    when = []
    if job["schedule"]: when += ["--on-calendar", job["schedule"]]
    if job["cwd"]: props += [f"--property=WorkingDirectory={job['cwd']}"]
    args = []
    if job.get("args"): args += json.loads(job["args"])
    unit = "job-" + str(job['id']) + ".service"
    return ["systemd-run", "--user", "--collect", "--quiet", "--unit", unit] + props + env + when + ["--", job['cmd']] + args, unit

def run_job(job, db):
    # Native execution (if not systemd)
    try:
        p = subprocess.run([job['cmd']] + json.loads(job.get('args') or "[]"),
                           env={**os.environ, **json.loads(job['env'] or "{}")},
                           text=True, capture_output=True, timeout=290)
        db.complete_job(job['id'], p.returncode == 0,
                        {'stdout': p.stdout[:1000],'stderr':p.stderr[:1000]},
                        p.stderr if p.returncode != 0 else None)
        print(f"Job {job['id']} {job['name']} finished. Code={p.returncode}")
    except subprocess.TimeoutExpired:
        db.complete_job(job['id'], False, error="TIMEOUT")
    except Exception as e:
        db.complete_job(job['id'], False, error=str(e))

def start_systemd(job, db):
    import subprocess
    args, unit = systemd_run_args(job)
    cp = subprocess.run(args, text=True, capture_output=True)
    status = "scheduled" if job["schedule"] else "started"
    db.update_unit(job["name"], unit, status)
    if cp.returncode == 0:
        print(f"{unit}: scheduled/started")
    else:
        print(f"ERROR [{unit}]: {cp.stderr.strip()}")

# ==== WORKER LOOP ====
def worker_loop(db, batch=1, use_systemd=False):
    wid = f"w{os.getpid()}"
    running=True
    def sig(_1,_2): nonlocal running; running=False
    try: import signal; signal.signal(signal.SIGTERM,sig); signal.signal(signal.SIGINT,sig)
    except: pass
    print(f"Worker {wid} started; batch={batch} systemd={use_systemd}")
    while running:
        tasks = []
        for _ in range(batch):
            t = db.pop_job(wid)
            if t: tasks.append(t)
        if not tasks:
            time.sleep(0.05)
            continue
        for task in tasks:
            if use_systemd: start_systemd(task, db)
            else: run_job(task, db)

# ==== CLI HANDLER ====
def main():
    ap = argparse.ArgumentParser(description="Unified Job Orchestrator")
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("add", help="Add new job")
    a.add_argument("name"); a.add_argument("command")
    a.add_argument("args", nargs="*")
    a.add_argument("--env", action="append", default=[], help="KEY=VAL")
    a.add_argument("--priority", type=int, default=0)
    a.add_argument("--delay", type=int, default=0)
    a.add_argument("--deps", default=None)
    a.add_argument("--schedule")
    a.add_argument("--rtprio", type=int)
    a.add_argument("--nice", type=int)
    a.add_argument("--slice")
    a.add_argument("--cpu-weight", type=int)
    a.add_argument("--mem-max-mb", type=int)
    a.add_argument("--start", action="store_true")
    w = sp.add_parser("worker", help="Run worker loop")
    w.add_argument("--batch", type=int, default=1)
    w.add_argument("--systemd", action="store_true")
    sp.add_parser("list", help="List all jobs")
    cln = sp.add_parser("cleanup", help="Clean old jobs")
    cln.add_argument("--days", type=int, default=7)
    st = sp.add_parser("status", help="Status of named job"); st.add_argument("name")
    sp.add_parser("bench", help="Benchmark inserts/perf")

    args = ap.parse_args()
    db = DB()
    if args.cmd == "add":
        env = {e.split('=',1)[0]:e.split('=',1)[1] for e in args.env} if args.env else {}
        deps = json.loads(args.deps) if args.deps else None
        at = int(time.time()*1000) + args.delay if args.delay else None
        job_id = db.add_job(name=args.name, cmd=args.command, args=args.args,
                            env=env, priority=args.priority, schedule=args.schedule,
                            at=at, dep=deps, rtprio=args.rtprio, nice=args.nice,
                            slice=args.slice, cpu_weight=args.cpu_weight,
                            mem_max_mb=args.mem_max_mb)
        print(f"Job {job_id} added")
        if args.start:
            job = db.get_job(job_id)
            run_job(job, db)
    elif args.cmd == "worker":
        worker_loop(db, batch=args.batch, use_systemd=args.systemd)
    elif args.cmd == "list":
        for r in db.list_jobs():
            print(f"{r['id']} {r['name']} [{r['status']}] unit={r['unit'] or '-'} sched={r['schedule'] or '-'}")
    elif args.cmd == "cleanup":
        deleted = db.cleanup_jobs(args.days)
        print(f"Deleted {deleted} old jobs")
    elif args.cmd == "status":
        job = db.get_job_by_name(args.name)
        print(json.dumps(dict(job) if job else {"error":"not found"}, indent=2))
    elif args.cmd == "bench":
        start = time.time()
        for i in range(1000):
            db.add_job(name=f"test{i}", cmd="echo", args=[str(i)])
        print(f"1000 inserts: {(time.time()-start)*1000:.2f}ms")
        print(f"List count: {len(db.list_jobs())}")

if __name__ == "__main__":
    main()
