#!/usr/bin/env python3
"""
Unified Job Orchestrator: Enhanced with best features from all implementations.
SQLite state, systemd execution, deps, retries, scheduling, metrics table.
Supports job ID or name in CLI. Bench for perf testing. Under 500 lines.
"""
import argparse, json, os, shlex, sqlite3, subprocess, sys, time
from pathlib import Path
from typing import Dict, Any, Optional, Union
DB = Path.home() / ".unified_orchestrator.db"
UNIT_PREFIX = "uniorch-"
SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"]
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=268435456",
    "PRAGMA busy_timeout=5000",
    "PRAGMA wal_autocheckpoint=1000",
]
def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True)
def ok(cp): return cp.returncode == 0
def unit_name(identifier: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-:" else "_" for c in identifier)
    return f"{UNIT_PREFIX}{safe}.service"
def db_conn():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for pragma in PRAGMAS:
        con.execute(pragma)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            cmd TEXT NOT NULL,
            args TEXT,
            env TEXT,
            cwd TEXT,
            schedule TEXT,
            scheduled_at INTEGER,
            priority INTEGER DEFAULT 0,
            deps TEXT,
            max_retries INTEGER DEFAULT 3,
            retry_count INTEGER DEFAULT 0,
            timeout_sec INTEGER,
            rtprio INTEGER,
            nice INTEGER,
            slice TEXT,
            cpu_weight INTEGER,
            mem_max_mb INTEGER,
            unit TEXT,
            status TEXT DEFAULT 'added',
            created_at INTEGER DEFAULT (strftime('%s','now')*1000),
            started_at INTEGER,
            ended_at INTEGER,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_queue ON jobs(status, priority DESC, scheduled_at, id)
        WHERE status IN ('added', 'queued', 'failed');
        CREATE TABLE IF NOT EXISTS metrics (
            job_id INTEGER PRIMARY KEY,
            queue_time REAL,
            exec_time REAL,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
    """)
    return con
def add_job(**kw) -> int:
    kw.setdefault("created_at", int(time.time() * 1000))
    with db_conn() as con:
        cursor = con.execute("""INSERT INTO jobs
            (name,cmd,args,env,cwd,schedule,scheduled_at,priority,deps,max_retries,retry_count,
             timeout_sec,rtprio,nice,slice,cpu_weight,mem_max_mb,unit,status,created_at,
             started_at,ended_at,error)
            VALUES(:name,:cmd,:args,:env,:cwd,:schedule,:scheduled_at,:priority,:deps,:max_retries,:retry_count,
                   :timeout_sec,:rtprio,:nice,:slice,:cpu_weight,:mem_max_mb,:unit,:status,:created_at,
                   :started_at,:ended_at,:error)""", kw)
        return cursor.lastrowid
def get_job(identifier: Union[int, str]) -> Optional[Dict[str, Any]]:
    with db_conn() as con:
        if isinstance(identifier, int):
            row = con.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
        else:
            row = con.execute("SELECT * FROM jobs WHERE name=?", (identifier,)).fetchone()
        if row:
            job = dict(row)
            job['args'] = json.loads(job['args']) if job['args'] else []
            job['env'] = json.loads(job['env']) if job['env'] else {}
            job['deps'] = json.loads(job['deps']) if job['deps'] else []
            return job
        return None
def list_jobs(status: Optional[str] = None) -> list:
    with db_conn() as con:
        if status:
            rows = con.execute("SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
def show(unit: str, *props: str) -> Dict[str, str]:
    out = sh(SYSTEMCTL + ["show", unit, *(["--property=" + p for p in props] if props else [])]).stdout
    return {k: v for k, v in (line.split("=", 1) for line in out.splitlines() if "=" in line)}
def start_transient(job: Dict[str, Any]) -> tuple[bool, str, str]:
    identifier = job["name"] or str(job["id"])
    unit = unit_name(identifier)
    props = [
        "--property=StandardOutput=journal",
        "--property=StandardError=journal",
        "--property=KillMode=control-group",
    ]
    if job["timeout_sec"]:
        props += [f"--property=TimeoutSec={job['timeout_sec']}"]
    if job["rtprio"]:
        props += ["--property=CPUSchedulingPolicy=rr", f"--property=CPUSchedulingPriority={job['rtprio']}"]
    calc_nice = job["nice"]
    if calc_nice is None and job["priority"] is not None:
        calc_nice = 10 - job["priority"]
    if calc_nice is not None:
        props += [f"--property=Nice={int(calc_nice)}"]
    if job["slice"]:
        props += [f"--slice={job['slice']}"]
    if job["cpu_weight"]:
        props += [f"--property=CPUWeight={job['cpu_weight']}"]
    if job["mem_max_mb"]:
        props += [f"--property=MemoryMax={int(job['mem_max_mb'])}M"]
    if job["cwd"]:
        props += [f"--property=WorkingDirectory={job['cwd']}"]
    env = []
    if job["env"]:
        for k, v in job["env"].items():
            env += ["--setenv", f"{k}={v}"]
    when = []
    persistent = False
    now_s = time.time()
    if job["schedule"]:
        when = ["--on-calendar", job["schedule"]]
        persistent = True
    elif job["scheduled_at"]:
        sched_s = job["scheduled_at"] / 1000.0
        delay_s = max(0, sched_s - now_s)
        if delay_s > 0:
            when = ["--on-active", f"{int(delay_s + 0.5)}s"]
            persistent = True
    if persistent:
        props += ["--property=Persistent=true"]
    cmd_args = [job["cmd"], *job["args"]]
    cp = sh([*SYSDRUN, "--unit", unit, *props, *env, *when, "--", *cmd_args])
    with db_conn() as con:
        new_status = "scheduled" if when else "started"
        con.execute("UPDATE jobs SET unit=?, status=? WHERE id=?", (unit, new_status, job["id"]))
    return ok(cp), unit, cp.stderr.strip() or cp.stdout.strip()
def stop(identifier: Union[int, str]):
    job = get_job(identifier)
    if not job or not job["unit"]:
        return
    unit = job["unit"]
    sh(SYSTEMCTL + ["stop", unit])
    sh(SYSTEMCTL + ["stop", unit.replace(".service", ".timer")])
    with db_conn() as con:
        con.execute("UPDATE jobs SET status='stopped', unit=NULL WHERE id=?", (job["id"],))
def job_status(identifier: Union[int, str]) -> Dict[str, Any]:
    job = get_job(identifier)
    if not job:
        return {"active": "unknown"}
    if not job["unit"]:
        return {"unit": None, "active": job["status"]}
    info = show(job["unit"], "ActiveState", "Result", "MainPID")
    return {"unit": job["unit"], "active": info.get("ActiveState"), "result": info.get("Result"), "pid": info.get("MainPID")}
def reconcile():
    now_ms = int(time.time() * 1000)
    with db_conn() as con:
        jobs = con.execute("SELECT * FROM jobs").fetchall()
        for row in jobs:
            job = dict(row)
            if job["unit"]:
                unit = job["unit"]
                info = show(unit, "ActiveState", "Result", "ExecMainStartTimestamp", "ExecMainExitTimestamp")
                active = info.get("ActiveState")
                if active in ("inactive", "failed"):
                    result = info.get("Result")
                    new_status = "completed" if result == "success" else "failed"
                    err = None if new_status == "completed" else f"Systemd result: {result}. See journalctl -u {unit}"
                    con.execute("UPDATE jobs SET status=?, error=?, ended_at=? WHERE id=?",
                                (new_status, err, now_ms, job["id"]))
                    # Record metrics
                    start_ts = info.get("ExecMainStartTimestamp")
                    end_ts = info.get("ExecMainExitTimestamp")
                    if start_ts and start_ts.isdigit() and end_ts and end_ts.isdigit():
                        started_at = int(int(start_ts) / 1000)
                        ended_at = int(int(end_ts) / 1000)
                        qt = (started_at - job["created_at"]) / 1000.0
                        et = (ended_at - started_at) / 1000.0
                        con.execute("INSERT OR REPLACE INTO metrics(job_id, queue_time, exec_time) VALUES(?,?,?)",
                                    (job["id"], qt, et))
                elif active == "active":
                    if job["status"] != "running":
                        con.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
                    start_ts = info.get("ExecMainStartTimestamp")
                    if start_ts and start_ts.isdigit() and not job["started_at"]:
                        started_at = int(int(start_ts) / 1000)
                        con.execute("UPDATE jobs SET started_at=? WHERE id=?", (started_at, job["id"]))
            if job["status"] in ("added", "failed"):
                if job["status"] == "failed" and job["retry_count"] >= job["max_retries"]:
                    continue
                deps_ok = True
                if job["deps"]:
                    for dep_id in job["deps"]:
                        dep = con.execute("SELECT status FROM jobs WHERE id=?", (dep_id,)).fetchone()
                        if not dep or dep["status"] != "completed":
                            deps_ok = False
                            break
                if not deps_ok:
                    continue
                if job["scheduled_at"] and job["scheduled_at"] > now_ms:
                    continue
                if job["status"] == "failed":
                    backoff_ms = job["retry_delay"] * (2 ** job["retry_count"])
                    if now_ms < (job["ended_at"] or 0) + backoff_ms:
                        continue
                    con.execute("UPDATE jobs SET retry_count=retry_count+1 WHERE id=?", (job["id"],))
                if job["unit"]:
                    stop(job["id"])
                ok_, unit, msg = start_transient(job)
                if not ok_:
                    continue
                con.execute("UPDATE jobs SET started_at=? WHERE id=? AND started_at IS NULL", (now_ms, job["id"]))
def stats() -> Dict[str, Any]:
    with db_conn() as con:
        counts = {r["status"]: r["c"] for r in con.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status")}
        perf = con.execute("""
            SELECT AVG(queue_time) avg_qt, AVG(exec_time) avg_et,
                   MAX(queue_time) max_qt, MAX(exec_time) max_et
            FROM metrics
        """).fetchone()
        return {"jobs": counts, "perf": dict(perf) if perf else {}}
def cleanup(days: int = 7) -> int:
    cutoff = int(time.time() * 1000) - (days * 86400000)
    with db_conn() as con:
        deleted = con.execute("DELETE FROM jobs WHERE status IN ('completed','failed') AND ended_at < ?", (cutoff,)).rowcount
        page_count = con.execute("PRAGMA page_count").fetchone()[0]
        freelist = con.execute("PRAGMA freelist_count").fetchone()[0]
        if freelist > page_count * 0.3:
            con.execute("VACUUM")
        return deleted
def systemd_unit():
    return f"""[Unit]
Description=Unified Job Orchestrator
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 {os.path.abspath(__file__)} run
Restart=always
RestartSec=3
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=10
LimitNOFILE=65536
Nice=-5
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target"""
def bench():
    db_file = "bench.db"
    if os.path.exists(db_file):
        os.unlink(db_file)
    db = JobOrchestrator(db_file)
    start = time.time()
    for i in range(1000):
        db.add_job(name=f"test{i}", cmd="echo", args=[str(i)], priority=i%10)
    ins_time = (time.time() - start) * 1000
    start = time.time()
    db.list_jobs()
    list_time = (time.time() - start) * 1000
    print(f"1000 inserts: {ins_time:.2f}ms\nList: {list_time:.2f}ms")
def main():
    ap = argparse.ArgumentParser(description="Unified Job Orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="add job")
    a.add_argument("name", nargs="?")
    a.add_argument("command")
    a.add_argument("args", nargs="*")
    a.add_argument("--env", action="append", default=[])
    a.add_argument("--cwd")
    a.add_argument("--schedule")
    a.add_argument("--delay-ms", type=int)
    a.add_argument("--priority", type=int)
    a.add_argument("--deps", help="comma-separated IDs")
    a.add_argument("--max-retries", type=int)
    a.add_argument("--timeout-sec", type=int)
    a.add_argument("--rtprio", type=int)
    a.add_argument("--nice", type=int)
    a.add_argument("--slice")
    a.add_argument("--cpu-weight", type=int)
    a.add_argument("--mem-max-mb", type=int)
    a.add_argument("--start", action="store_true")
    l = sub.add_parser("list", help="list jobs")
    l.add_argument("--status")
    s = sub.add_parser("start", help="start job")
    s.add_argument("identifier")
    t = sub.add_parser("stop", help="stop job")
    t.add_argument("identifier")
    u = sub.add_parser("status", help="job status")
    u.add_argument("identifier")
    sub.add_parser("reconcile", help="reconcile states")
    sub.add_parser("run", help="run reconciler loop")
    sub.add_parser("stats", help="show stats")
    c = sub.add_parser("cleanup", help="cleanup old")
    c.add_argument("--days", type=int, default=7)
    sub.add_parser("systemd", help="generate unit file")
    sub.add_parser("bench", help="run benchmark")
    args = ap.parse_args()
    if args.cmd == "add":
        env_d = dict(e.split("=", 1) for e in args.env) if args.env else {}
        deps_l = [int(d) for d in args.deps.split(",")] if args.deps else []
        name = args.name or f"job-{int(time.time())}"
        job_id = add_job(
            name=name, cmd=args.command, args=json.dumps(args.args),
            env=json.dumps(env_d), cwd=args.cwd, schedule=args.schedule,
            scheduled_at=(args.delay_ms + int(time.time() * 1000) if args.delay_ms else None),
            priority=args.priority, deps=json.dumps(deps_l), max_retries=args.max_retries,
            timeout_sec=args.timeout_sec, rtprio=args.rtprio, nice=args.nice, slice=args.slice,
            cpu_weight=args.cpu_weight, mem_max_mb=args.mem_max_mb, unit=None, status="added",
            started_at=None, ended_at=None, error=None
        )
        print(f"Added job ID: {job_id} Name: {name}")
        if args.start:
            job = get_job(job_id)
            ok_, unit, msg = start_transient(job)
            print(unit if ok_ else f"ERROR: {msg}")
    elif args.cmd == "list":
        reconcile()
        jobs = list_jobs(args.status)
        if jobs:
            print("| ID | Name | Status | Unit | Schedule |")
            print("|--- |---- |------ |---- |-------- |")
            for job in jobs:
                sched = job["schedule"] or job["scheduled_at"] or "-"
                print(f"| {job['id']} | {job['name'] or '-'} | {job['status']} | {job['unit'] or '-'} | {sched} |")
        else:
            print("No jobs")
    elif args.cmd == "start":
        job = get_job(args.identifier)
        if not job:
            sys.exit("unknown job")
        ok_, unit, msg = start_transient(job)
        print(unit if ok_ else f"ERROR: {msg}")
    elif args.cmd == "stop":
        stop(args.identifier)
        print("stopped")
    elif args.cmd == "status":
        print(json.dumps(job_status(args.identifier), indent=2))
    elif args.cmd == "reconcile":
        reconcile()
        print("ok")
    elif args.cmd == "run":
        print("Orchestrator running...")
        while True:
            reconcile()
            time.sleep(1)
    elif args.cmd == "stats":
        print(json.dumps(stats(), indent=2))
    elif args.cmd == "cleanup":
        deleted = cleanup(args.days)
        print(f"Deleted {deleted} old jobs")
    elif args.cmd == "systemd":
        print(systemd_unit())
    elif args.cmd == "bench":
        bench()
if __name__ == "__main__":
    main()