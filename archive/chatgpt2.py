#!/usr/bin/env python3
# aios_systemd_orchestrator.py — best-of synthesis (<200 lines)
# - Transient user units & timers (systemd-run) = no zombies, auto cgroups
# - RT scheduling & nice via properties; optional slice/limits
# - Single SQLite DB for state; simple CLI
import argparse, json, os, shlex, sqlite3, subprocess, sys, time
from pathlib import Path

DB = Path.home() / ".aios_tasks.db"
UNIT_PREFIX = "aios-"
SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"]

def sh(cmd:list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True)

def ok(cp): return cp.returncode == 0

def unit_name(name:str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-:" else "_" for c in name)
    return f"{UNIT_PREFIX}{safe}.service"

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
      PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS jobs(
        name TEXT PRIMARY KEY, cmd TEXT NOT NULL, args TEXT,
        env TEXT, cwd TEXT, schedule TEXT, rtprio INTEGER,
        nice INTEGER, slice TEXT, cpu_weight INTEGER, mem_max_mb INTEGER,
        unit TEXT, status TEXT DEFAULT 'added', created_at INTEGER
      );
    """)
    return con

def add_job(**kw):
    kw.setdefault("created_at", int(time.time()))
    with db() as con:
        con.execute("""INSERT OR REPLACE INTO jobs
        (name,cmd,args,env,cwd,schedule,rtprio,nice,slice,cpu_weight,mem_max_mb,unit,status,created_at)
        VALUES(:name,:cmd,:args,:env,:cwd,:schedule,:rtprio,:nice,:slice,:cpu_weight,:mem_max_mb,:unit,:status,:created_at)""", kw)

def list_jobs():
    with db() as con:
        return con.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()

def show(unit:str, *props:str) -> dict:
    out = sh(SYSTEMCTL + ["show", unit, *(["--property="+p for p in props] if props else [])]).stdout
    return {k:v for k,v in (line.split("=",1) for line in out.splitlines() if "=" in line)}

def start_transient(job:sqlite3.Row):
    unit = unit_name(job["name"])
    props = [
        "--property=StandardOutput=journal",
        "--property=StandardError=journal",
        "--property=KillMode=control-group",
    ]
    if job["rtprio"]: props += ["--property=CPUSchedulingPolicy=rr",
                                f"--property=CPUSchedulingPriority={job['rtprio']}"]
    if job["nice"] is not None: props += [f"--property=Nice={int(job['nice'])}"]
    if job["slice"]: props += [f"--slice={job['slice']}"]
    if job["cpu_weight"]: props += [f"--property=CPUWeight={job['cpu_weight']}"]
    if job["mem_max_mb"]: props += [f"--property=MemoryMax={int(job['mem_max_mb'])}M"]
    env = []
    if job["env"]:
        for k,v in json.loads(job["env"]).items():
            env += ["--setenv", f"{k}={v}"]
    when = []
    if job["schedule"]: when += ["--on-calendar", job["schedule"]]
    if job["cwd"]: props += [f"--property=WorkingDirectory={job['cwd']}"]

    cmd = [*SYSDRUN, "--unit", unit, *props, *env, *when, "--", job["cmd"], *json.loads(job["args"] or "[]")]
    cp = sh(cmd)
    with db() as con:
        con.execute("UPDATE jobs SET unit=?, status=? WHERE name=?", (unit, "scheduled" if job["schedule"] else "started", job["name"]))
    return ok(cp), unit, cp.stderr.strip() or cp.stdout.strip()

def stop(name:str):
    unit = unit_name(name)
    sh(SYSTEMCTL + ["stop", unit])
    sh(SYSTEMCTL + ["stop", unit.replace(".service",".timer")])
    with db() as con:
        con.execute("UPDATE jobs SET status='stopped' WHERE name=?", (name,))

def status(name:str):
    unit = unit_name(name)
    info = show(unit, "ActiveState","Result","MainPID")
    if not info: return {"unit":unit,"active":"unknown"}
    return {"unit":unit,"active":info.get("ActiveState"),"result":info.get("Result"),"pid":info.get("MainPID")}

def set_rt(name:str, policy="fifo", prio=20):
    unit = unit_name(name)
    return sh(SYSTEMCTL + ["set-property", unit, f"CPUSchedulingPolicy={policy}", f"CPUSchedulingPriority={prio}"]).stdout

def reconcile():
    # Mark finished jobs by querying unit state
    with db() as con:
        for r in con.execute("SELECT name,unit,status FROM jobs WHERE unit IS NOT NULL"):
            info = show(r["unit"], "ActiveState","Result")
            if info and info.get("ActiveState") in ("inactive","failed"):
                new = "completed" if info.get("Result") == "success" else "failed"
                con.execute("UPDATE jobs SET status=? WHERE name=?", (new, r["name"]))

def main():
    ap = argparse.ArgumentParser(description="AIOS systemd orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="record & (optionally) start a job")
    a.add_argument("name"); a.add_argument("command"); a.add_argument("args", nargs="*")
    a.add_argument("--env", action="append", default=[], help="KEY=VAL")
    a.add_argument("--cwd"); a.add_argument("--on-calendar")
    a.add_argument("--rtprio", type=int); a.add_argument("--nice", type=int)
    a.add_argument("--slice"); a.add_argument("--cpu-weight", type=int); a.add_argument("--mem-max-mb", type=int)
    a.add_argument("--start", action="store_true")

    sub.add_parser("list", help="list jobs")
    s = sub.add_parser("start", help="start existing job"); s.add_argument("name")
    t = sub.add_parser("stop", help="stop job"); t.add_argument("name")
    u = sub.add_parser("status", help="status"); u.add_argument("name")
    r = sub.add_parser("set-rt", help="tune RT"); r.add_argument("name"); r.add_argument("--policy", default="fifo"); r.add_argument("--prio", type=int, default=20)
    sub.add_parser("reconcile", help="refresh job statuses")

    args = ap.parse_args()

    if args.cmd == "add":
        env = dict(e.split("=",1) for e in args.env) if args.env else {}
        add_job(
            name=args.name, cmd=args.command, args=json.dumps(args.args),
            env=json.dumps(env) if env else None, cwd=args.cwd, schedule=args.on_calendar,
            rtprio=args.rtprio, nice=args.nice, slice=args.slice,
            cpu_weight=args.cpu_weight, mem_max_mb=args.mem_max_mb, unit=None, status="added"
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
            print(f"{r['name']}: {r['status']}  unit={r['unit'] or '-'}  sched={r['schedule'] or '-'}")

    elif args.cmd == "start":
        with db() as con:
            row = con.execute("SELECT * FROM jobs WHERE name=?", (args.name,)).fetchone()
        if not row: sys.exit("unknown job")
        ok_, unit, msg = start_transient(row)
        print(unit if ok_ else f"ERROR: {msg}")

    elif args.cmd == "stop":
        stop(args.name); print("stopped")

    elif args.cmd == "status":
        print(json.dumps(status(args.name), indent=2))

    elif args.cmd == "set-rt":
        print(set_rt(args.name, args.policy, args.prio).strip())

    elif args.cmd == "reconcile":
        reconcile(); print("ok")

if __name__ == "__main__":
    main()
