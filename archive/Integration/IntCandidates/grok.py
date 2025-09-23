#!/usr/bin/env python3
"""
Integrated Job Orchestrator: Combines task queue with systemd management.
Uses SQLite for state, systemd for processes, supports deps, retries, scheduling.
"""
import argparse, json, os, shlex, sqlite3, subprocess, sys, time
from pathlib import Path
from typing import Dict, Any, Optional

DB = Path.home() / ".orchestrator_tasks.db"
UNIT_PREFIX = "orch-"
SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"]
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA busy_timeout=5000",
    "PRAGMA wal_autocheckpoint=1000",
]

def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True)

def ok(cp): return cp.returncode == 0

def unit_name(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-:" else "_" for c in name)
    return f"{UNIT_PREFIX}{safe}.service"

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for pragma in PRAGMAS:
        con.execute(pragma)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(
            name TEXT PRIMARY KEY,
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
            created_at INTEGER,
            started_at INTEGER,
            ended_at INTEGER,
            error TEXT
        );
    """)
    return con

def add_job(**kw):
    kw.setdefault("created_at", int(time.time() * 1000))
    with db() as con:
        con.execute("""INSERT OR REPLACE INTO jobs
            (name,cmd,args,env,cwd,schedule,scheduled_at,priority,deps,max_retries,retry_count,timeout_sec,
             rtprio,nice,slice,cpu_weight,mem_max_mb,unit,status,created_at,started_at,ended_at,error)
            VALUES(:name,:cmd,:args,:env,:cwd,:schedule,:scheduled_at,:priority,:deps,:max_retries,:retry_count,
                   :timeout_sec,:rtprio,:nice,:slice,:cpu_weight,:mem_max_mb,:unit,:status,:created_at,
                   :started_at,:ended_at,:error)""", kw)

def list_jobs():
    with db() as con:
        return con.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()

def show(unit: str, *props: str) -> Dict[str, str]:
    out = sh(SYSTEMCTL + ["show", unit, *(["--property=" + p for p in props] if props else [])]).stdout
    return {k: v for k, v in (line.split("=", 1) for line in out.splitlines() if "=" in line)}

def start_transient(job: sqlite3.Row) -> tuple[bool, str, str]:
    unit = unit_name(job["name"])
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
        calc_nice = 10 - job["priority"]  # Higher priority -> lower nice
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
        for k, v in json.loads(job["env"]).items():
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
            when = ["--on-active", f"{int(delay_s + 0.5)}s"]  # Round up
            persistent = True
    if persistent:
        props += ["--property=Persistent=true"]
    cmd_args = [job["cmd"], *json.loads(job["args"] or "[]")]
    cp = sh([*SYSDRUN, "--unit", unit, *props, *env, *when, "--", *cmd_args])
    with db() as con:
        new_status = "scheduled" if when else "started"
        con.execute("UPDATE jobs SET unit=?, status=? WHERE name=?", (unit, new_status, job["name"]))
    return ok(cp), unit, cp.stderr.strip() or cp.stdout.strip()

def stop(name: str):
    with db() as con:
        row = con.execute("SELECT unit FROM jobs WHERE name=?", (name,)).fetchone()
        if not row or not row["unit"]:
            return
    unit = row["unit"]
    sh(SYSTEMCTL + ["stop", unit])
    sh(SYSTEMCTL + ["stop", unit.replace(".service", ".timer")])
    with db() as con:
        con.execute("UPDATE jobs SET status='stopped', unit=NULL WHERE name=?", (name,))

def status(name: str) -> Dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT unit, status FROM jobs WHERE name=?", (name,)).fetchone()
        if not row:
            return {"active": "unknown"}
    if not row["unit"]:
        return {"unit": None, "active": row["status"]}
    info = show(row["unit"], "ActiveState", "Result", "MainPID")
    return {"unit": row["unit"], "active": info.get("ActiveState"), "result": info.get("Result"), "pid": info.get("MainPID")}

def reconcile():
    now_ms = int(time.time() * 1000)
    with db() as con:
        jobs = con.execute("SELECT * FROM jobs").fetchall()
        for job in jobs:
            if job["unit"]:
                unit = job["unit"]
                info = show(unit, "ActiveState", "Result", "ExecMainStartTimestamp", "ExecMainExitTimestamp")
                active = info.get("ActiveState")
                if active in ("inactive", "failed"):
                    result = info.get("Result")
                    if active == "failed" or result != "success":
                        new_status = "failed"
                        err = f"see journalctl --user -u {unit}"
                        con.execute("UPDATE jobs SET status=?, error=?, ended_at=? WHERE name=?",
                                    (new_status, err, now_ms, job["name"]))
                    else:
                        new_status = "completed"
                        con.execute("UPDATE jobs SET status=?, ended_at=? WHERE name=?",
                                    (new_status, now_ms, job["name"]))
                elif active == "active":
                    if job["status"] != "running":
                        con.execute("UPDATE jobs SET status='running' WHERE name=?", (job["name"],))
                    start_ts = info.get("ExecMainStartTimestamp")
                    if start_ts and start_ts.isdigit() and not job["started_at"]:
                        started_at = int(int(start_ts) / 1000)
                        con.execute("UPDATE jobs SET started_at=? WHERE name=?", (started_at, job["name"]))
            if job["status"] in ("added", "failed"):
                if job["status"] == "failed" and job["retry_count"] >= job["max_retries"]:
                    continue
                deps_ok = True
                if job["deps"]:
                    deps = json.loads(job["deps"])
                    for dname in deps:
                        drow = con.execute("SELECT status FROM jobs WHERE name=?", (dname,)).fetchone()
                        if not drow or drow["status"] != "completed":
                            deps_ok = False
                            break
                if not deps_ok:
                    continue
                if job["scheduled_at"] and job["scheduled_at"] > now_ms:
                    continue
                if job["status"] == "failed":
                    backoff_ms = 1000 * (2 ** job["retry_count"])
                    if now_ms < (job["ended_at"] or 0) + backoff_ms:
                        continue
                if job["unit"]:
                    stop(job["name"])
                if job["status"] == "failed":
                    con.execute("UPDATE jobs SET retry_count=retry_count+1 WHERE name=?", (job["name"],))
                ok_, unit, msg = start_transient(job)
                if not ok_:
                    continue
                con.execute("UPDATE jobs SET started_at=? WHERE name=? AND started_at IS NULL", (now_ms, job["name"]))

def stats() -> Dict[str, Any]:
    with db() as con:
        counts = {r["status"]: r["c"] for r in con.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status")}
        perf = con.execute("""
            SELECT AVG(started_at - created_at)/1000.0 avg_qt,
                   AVG(ended_at - started_at)/1000.0 avg_et
            FROM jobs WHERE ended_at IS NOT NULL AND started_at IS NOT NULL
        """).fetchone()
        return {"tasks": counts, "perf": dict(perf) if perf else {}}

def cleanup(days: int = 7) -> int:
    cutoff = int(time.time() * 1000) - (days * 86400000)
    with db() as con:
        deleted = con.execute("DELETE FROM jobs WHERE status IN ('completed','failed') AND ended_at < ?", (cutoff,)).rowcount
        page_count = con.execute("PRAGMA page_count").fetchone()[0]
        freelist = con.execute("PRAGMA freelist_count").fetchone()[0]
        if freelist > page_count * 0.3:
            con.execute("VACUUM")
        return deleted

def systemd_unit():
    return f"""[Unit]
Description=Job Orchestrator Reconciler
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

def main():
    ap = argparse.ArgumentParser(description="Job Orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="add job")
    a.add_argument("name")
    a.add_argument("command")
    a.add_argument("args", nargs="*")
    a.add_argument("--env", action="append", default=[])
    a.add_argument("--cwd")
    a.add_argument("--schedule")
    a.add_argument("--delay-ms", type=int)
    a.add_argument("--priority", type=int)
    a.add_argument("--deps")
    a.add_argument("--max-retries", type=int)
    a.add_argument("--timeout-sec", type=int)
    a.add_argument("--rtprio", type=int)
    a.add_argument("--nice", type=int)
    a.add_argument("--slice")
    a.add_argument("--cpu-weight", type=int)
    a.add_argument("--mem-max-mb", type=int)
    a.add_argument("--start", action="store_true")
    sub.add_parser("list")
    s = sub.add_parser("start")
    s.add_argument("name")
    t = sub.add_parser("stop")
    t.add_argument("name")
    u = sub.add_parser("status")
    u.add_argument("name")
    sub.add_parser("reconcile")
    sub.add_parser("run", help="run reconciler loop")
    sub.add_parser("stats")
    c = sub.add_parser("cleanup")
    c.add_argument("days", type=int, nargs="?", default=7)
    sub.add_parser("systemd", help="generate systemd unit")
    args = ap.parse_args()
    if args.cmd == "add":
        env_d = dict(e.split("=", 1) for e in args.env) if args.env else {}
        deps_l = args.deps.split(",") if args.deps else []
        add_job(
            name=args.name, cmd=args.command, args=json.dumps(args.args),
            env=json.dumps(env_d) if env_d else None, cwd=args.cwd, schedule=args.schedule,
            scheduled_at=args.delay_ms + int(time.time() * 1000) if args.delay_ms else None,
            priority=args.priority, deps=json.dumps(deps_l), max_retries=args.max_retries,
            timeout_sec=args.timeout_sec, rtprio=args.rtprio, nice=args.nice, slice=args.slice,
            cpu_weight=args.cpu_weight, mem_max_mb=args.mem_max_mb, unit=None, status="added",
            started_at=None, ended_at=None, error=None
        )
        if args.start:
            with db() as con:
                row = con.execute("SELECT * FROM jobs WHERE name=?", (args.name,)).fetchone()
            ok_, unit, msg = start_transient(row)
            print(unit if ok_ else f"ERROR: {msg}")
        else:
            print("added")
    elif args.cmd == "list":
        reconcile()
        for r in list_jobs():
            print(f"{r['name']}: {r['status']}  unit={r['unit'] or '-'}  sched={r['schedule'] or r['scheduled_at'] or '-'}")
    elif args.cmd == "start":
        with db() as con:
            row = con.execute("SELECT * FROM jobs WHERE name=?", (args.name,)).fetchone()
        if not row:
            sys.exit("unknown job")
        ok_, unit, msg = start_transient(row)
        print(unit if ok_ else f"ERROR: {msg}")
    elif args.cmd == "stop":
        stop(args.name)
        print("stopped")
    elif args.cmd == "status":
        print(json.dumps(status(args.name), indent=2))
    elif args.cmd == "reconcile":
        reconcile()
        print("ok")
    elif args.cmd == "run":
        print("Orchestrator running...")
        while True:
            reconcile()
            time.sleep(0.5)
    elif args.cmd == "stats":
        print(json.dumps(stats(), indent=2))
    elif args.cmd == "cleanup":
        deleted = cleanup(args.days)
        print(f"Deleted {deleted} old jobs")
    elif args.cmd == "systemd":
        print(systemd_unit())

if __name__ == "__main__":
    main()