#!/usr/bin/env python3
"""
aiosq – tiny unified job-queue + systemd orchestrator
One SQLite file (~/.aiosq.db) + systemd-run for cgroups, auto cleanup, no zombies.
"""
from __future__ import annotations
import argparse, json, os, shlex, sqlite3, subprocess, sys, time, signal, threading
from pathlib import Path
from typing import Dict, Any, Optional, List

DB_PATH   = Path.home() / ".aiosq.db"
UNIT_PREF = "aiosq-"
SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN   = ["systemd-run", "--user", "--collect", "--quiet"]

# ---------- SQLite helpers ---------------------------------------------------
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript("""
        PRAGMA journal_mode=WAL;  PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS t(
            id INTEGER PRIMARY KEY,
            cmd TEXT NOT NULL,
            p  INTEGER DEFAULT 0,               -- priority
            s  TEXT DEFAULT 'q',                -- status
            at INTEGER DEFAULT 0,               -- scheduled_at ms
            w  TEXT,                            -- worker
            r  INTEGER DEFAULT 0,               -- retry
            e  TEXT,                            -- error
            res TEXT,                           -- result
            ct INTEGER DEFAULT (unixepoch()*1000),
            st INTEGER, et INTEGER,             -- start/end
            dep TEXT                            -- json list
        );
        CREATE INDEX IF NOT EXISTS ix ON t(s,p DESC,at,id) WHERE s IN ('q','r');
    """)
    return c

LOCK = threading.RLock()

# ---------- Core queue ops ---------------------------------------------------
def add(cmd:str, p:int=0, at:int=0, dep:Optional[List[int]]=None) -> int:
    with LOCK:
        return conn().execute(
            "INSERT INTO t(cmd,p,at,dep) VALUES(?,?,?,?)",
            (cmd, p, at or int(time.time()*1000), json.dumps(dep) if dep else None)
        ).lastrowid

def pop(worker:str) -> Optional[Dict[str,Any]]:
    now = int(time.time()*1000)
    with LOCK:
        row = conn().execute("""
            SELECT id,cmd FROM t
            WHERE s='q' AND at<=? AND
                  (dep IS NULL OR NOT EXISTS(
                      SELECT 1 FROM json_each(t.dep) j JOIN t d ON d.id=j.value WHERE d.s!='d'))
            ORDER BY p DESC,at,id LIMIT 1
        """, (now,)).fetchone()
        if not row: return None
        conn().execute("UPDATE t SET s='r',w=?,st=? WHERE id=? AND s='q'", (worker,now,row['id']))
        return dict(row)

def done(task_id:int, ok:bool=True, worker:str="", err:str=""):
    now = int(time.time()*1000)
    with LOCK:
        if ok:
            conn().execute("UPDATE t SET s='d',et=?,w=NULL,res=? WHERE id=? AND w=?",
                           (now, json.dumps(err) if err else None, task_id, worker))
        else:
            row = conn().execute("SELECT r FROM t WHERE id=? AND w=?", (task_id,worker)).fetchone()
            if row and row['r']<3:
                delay = 1000*(2**row['r'])
                conn().execute("UPDATE t SET s='q',at=?,r=r+1,e=?,w=NULL WHERE id=?",
                               (now+delay,err,task_id))
            else:
                conn().execute("UPDATE t SET s='f',et=?,e=?,w=NULL WHERE id=?", (now,err,task_id))

# ---------- systemd helpers --------------------------------------------------
def unit(name:str) -> str: return f"{UNIT_PREF}{name.replace('/','_')}.service"
def sh(cmd): return subprocess.run(cmd,text=True,capture_output=True)

def start_transient(name:str, cmdline:str, env:dict=None, nice:int=None, rtprio:int=None,
                    slice:str=None, cpuw:int=None, mem:int=None, sched:str=None):
    props = ["--property=StandardOutput=journal", "--property=StandardError=journal"]
    if nice is not None: props.append(f"--property=Nice={nice}")
    if rtprio: props += ["--property=CPUSchedulingPolicy=rr", f"--property=CPUSchedulingPriority={rtprio}"]
    if slice: props.append(f"--slice={slice}")
    if cpuw: props.append(f"--property=CPUWeight={cpuw}")
    if mem: props.append(f"--property=MemoryMax={mem}M")
    eargs = []
    if env:
        for k,v in env.items(): eargs += ["--setenv",f"{k}={v}"]
    when = []
    if sched: when += ["--on-calendar", sched]
    u = unit(name)
    full = [*SYSDRUN, "--unit", u, *props, *eargs, *when, "--", *shlex.split(cmdline)]
    cp = sh(full)
    return cp.returncode==0, u, cp.stderr or cp.stdout

# ---------- Worker loop ------------------------------------------------------
class Worker:
    def __init__(self, batch:int=1):
        self.batch = batch
        self.running = True
        signal.signal(signal.SIGTERM, lambda *_: setattr(self,'running',False))
        signal.signal(signal.SIGINT,  lambda *_: setattr(self,'running',False))

    def run(self):
        wid = f"w{os.getpid()}"
        print(f"Worker {wid} started (batch={self.batch})")
        while self.running:
            tasks = []
            for _ in range(self.batch):
                t = pop(wid)
                if t: tasks.append(t)
            if not tasks:
                time.sleep(.05); continue
            for t in tasks:
                if not self.running: break
                try:
                    res = subprocess.run(t['cmd'], shell=True, capture_output=True,
                                         text=True, timeout=290)
                    done(t['id'], res.returncode==0, wid,
                         err=res.stderr[:500] if res.returncode else None)
                except Exception as e:
                    done(t['id'], False, wid, err=str(e))

# ---------- CLI --------------------------------------------------------------
def stats():
    c = conn()
    counts = {r['s']:r['c'] for r in c.execute("SELECT s,COUNT(*) c FROM t GROUP BY s")}
    return {"tasks":counts}

def cleanup(days:int=7):
    cutoff = int(time.time()*1000)-days*86400*1000
    with LOCK:
        deleted = conn().execute("DELETE FROM t WHERE s IN ('d','f') AND et<?",(cutoff,)).rowcount
    return deleted

def cli():
    ap = argparse.ArgumentParser(description="aiosq – queue + systemd orchestrator")
    sp = ap.add_subparsers(dest="cmd",required=True)

    a = sp.add_parser("add", help="add task")
    a.add_argument("cmd"); a.add_argument("-p","--priority",type=int,default=0)
    a.add_argument("-d","--delay",type=int,default=0)
    a.add_argument("--dep",type=int,nargs="+")

    sp.add_parser("worker").add_argument("-b","--batch",type=int,default=1)
    sp.add_parser("stats")
    c = sp.add_parser("cleanup"); c.add_argument("days",type=int,nargs="?",default=7)

    r = sp.add_parser("run", help="run via systemd")
    r.add_argument("name"); r.add_argument("cmdline")
    r.add_argument("--nice",type=int); r.add_argument("--rtprio",type=int)
    r.add_argument("--slice"); r.add_argument("--cpu-weight",type=int)
    r.add_argument("--mem-max",type=int)
    r.add_argument("--on-calendar"); r.add_argument("--env",action="append",default=[])

    s = sp.add_parser("stop"); s.add_argument("name")
    st = sp.add_parser("status"); st.add_argument("name")

    args = ap.parse_args()

    if args.cmd == "add":
        at = int(time.time()*1000)+args.delay if args.delay else 0
        tid = add(args.cmd, args.priority, at, args.dep)
        print(tid)

    elif args.cmd == "worker":
        Worker(args.batch).run()

    elif args.cmd == "stats":
        print(json.dumps(stats(),indent=2))

    elif args.cmd == "cleanup":
        print(cleanup(args.days))

    elif args.cmd == "run":
        env = dict(e.split("=",1) for e in args.env) if args.env else {}
        ok,u,msg = start_transient(args.name, args.cmdline, env, args.nice, args.rtprio,
                                   args.slice, args.cpu_weight, args.mem_max, args.on_calendar)
        print(u if ok else f"error: {msg}")

    elif args.cmd == "stop":
        u = unit(args.name)
        sh(SYSTEMCTL + ["stop", u])
        sh(SYSTEMCTL + ["stop", u.replace(".service",".timer")])
        print("stopped")

    elif args.cmd == "status":
        info = sh(SYSTEMCTL + ["show", unit(args.name), "--property=ActiveState,Result,MainPID"]).stdout
        print(info or "unknown")

if __name__ == "__main__":
    cli()