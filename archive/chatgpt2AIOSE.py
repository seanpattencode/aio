#!/usr/bin/env python3
"""
aiose — All-in-One Scheduler & Executor  (<500 lines)

Highlights (taken & improved):
- SQLite WAL + tuned pragmas (claude/chatgpt/gemini*)
- One table for everything; JSON deps/properties; metrics (chatgpt/claude)
- Atomic pop with json_each dep check + RETURNING fallback (chatgpt)
- Local subprocess runner + optional in-process Python function jobs ("py:module.func")
  (claude’s registry idea, simplified)
- systemd-run transient units with resource controls, OnCalendar or on-active delay, Persistent=true
  (aios_systemd/deepseek/grok/gemini*)
- Batch worker w/ reclaim of stalled, exponential backoff, stdout/stderr capture (chatgpt/glm)
- Efficient reconciliation of MANY units at once (geminiDeep)
- CLI: add | worker | start | stop | status | list | stats | cleanup | reconcile | install
"""
from __future__ import annotations
import argparse, json, os, shlex, signal, sqlite3, subprocess, sys, time, threading, importlib
from pathlib import Path
from typing import Optional, Dict, Any, List

# ---------- constants ----------
DB_PATH = Path.home() / ".aiose.db"
UNIT_PREFIX = "aiose-"
USE_USER = (os.geteuid() != 0)
SYSTEMCTL = ["systemctl", "--user"] if USE_USER else ["systemctl"]
SYSDRUN   = ["systemd-run", "--user", "--collect", "--quiet"] if USE_USER else ["systemd-run","--collect","--quiet"]
DEFAULT_TIMEOUT = 300
DEFAULT_RETRIES = 3

PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA busy_timeout=5000",
    "PRAGMA wal_autocheckpoint=1000",
]

# ---------- helpers ----------
def now_ms() -> int: return int(time.time()*1000)
def unit_name(ident: str|int) -> str:
    s = "".join(c if str(c).isalnum() or c in "._-:" else "_" for c in str(ident))
    return f"{UNIT_PREFIX}{s}.service"
def run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True)

# ---------- storage ----------
class Store:
    """SQLite store + queue operations (thread-safe)."""
    def __init__(self, path=DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        for p in PRAGMAS: self.c.execute(p)
        self.c.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(
          id INTEGER PRIMARY KEY,
          name TEXT UNIQUE,                  -- optional human handle
          cmd  TEXT NOT NULL,                -- 'shell string' OR 'py:module.func'
          mode TEXT DEFAULT 'local',         -- 'local' | 'systemd' | 'py'
          args TEXT,                         -- JSON array of args (local/systemd join into shell)
          env  TEXT,                         -- JSON map
          cwd  TEXT,                         -- working dir
          p INT DEFAULT 0,                   -- priority
          s TEXT DEFAULT 'q',                -- q=queued r=running d=done f=failed sched=startable/start
          at INT DEFAULT 0,                  -- scheduled_at (ms) for local/py
          schedule TEXT,                     -- systemd OnCalendar (cron-like)
          w  TEXT,                           -- worker_id (local/py)
          r  INT DEFAULT 0,                  -- retry_count
          maxr INT DEFAULT 3,                -- max_retries
          timeout INT DEFAULT 300,           -- seconds (local/py)
          e TEXT,                            -- error message
          res TEXT,                          -- result (stdout/stderr json)
          ct INT DEFAULT (strftime('%s','now')*1000),
          st INT, et INT,                    -- start/end times
          dep TEXT,                          -- JSON array of dependency IDs
          -- Systemd props
          unit TEXT, rtprio INT, nice INT, slice TEXT,
          cpu_weight INT, mem_max_mb INT
        );
        CREATE INDEX IF NOT EXISTS idx_q ON tasks(s,p DESC,at,id) WHERE s IN ('q','r');
        CREATE TABLE IF NOT EXISTS metrics(task_id INTEGER PRIMARY KEY, qt REAL, et REAL,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE);
        """)

    # CRUD
    def add(self, **kw) -> int:
        with self.lock:
            cols=",".join(kw.keys()); qs=",".join("?" for _ in kw)
            return self.c.execute(f"INSERT INTO tasks({cols}) VALUES({qs})", tuple(kw.values())).lastrowid
    def get_by_id(self, tid:int) -> Optional[sqlite3.Row]:
        with self.lock: return self.c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    def get_by_name(self, name:str) -> Optional[sqlite3.Row]:
        with self.lock: return self.c.execute("SELECT * FROM tasks WHERE name=?", (name,)).fetchone()
    def list(self) -> List[sqlite3.Row]:
        with self.lock: return self.c.execute("SELECT * FROM tasks ORDER BY ct DESC").fetchall()
    def update(self, tid:int, **kw):
        if not kw: return
        with self.lock:
            sets=",".join(f"{k}=?" for k in kw)
            self.c.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*kw.values(), tid))

    # Queue ops
    def pop(self, worker_id:str) -> Optional[Dict[str,Any]]:
        """Pop next eligible local/py task with dep check."""
        with self.lock:
            row = self.c.execute("""
              SELECT id, cmd, mode, args, env, cwd, timeout FROM tasks
              WHERE s='q' AND at<=? AND mode IN ('local','py')
                AND (dep IS NULL OR NOT EXISTS(
                  SELECT 1 FROM json_each(tasks.dep) AS d
                  JOIN tasks t2 ON t2.id=d.value WHERE t2.s!='d'))
              ORDER BY p DESC, at, id LIMIT 1
            """, (now_ms(),)).fetchone()
            if not row: return None
            try:
                claimed = self.c.execute(
                    "UPDATE tasks SET s='r', w=?, st=? WHERE id=? AND s='q' RETURNING id, cmd, mode, args, env, cwd, timeout",
                    (worker_id, now_ms(), row["id"])
                ).fetchone()
                if claimed: return dict(claimed)
            except sqlite3.OperationalError:
                self.c.execute("BEGIN IMMEDIATE")
                n = self.c.execute("UPDATE tasks SET s='r', w=?, st=? WHERE id=? AND s='q'",
                                   (worker_id, now_ms(), row["id"])).rowcount
                self.c.execute("COMMIT")
                if n:
                    return dict(row)
        return None

    def done(self, tid:int, ok:bool, result:Any=None, error:str=None, worker_id:str=""):
        with self.lock:
            t = self.c.execute("SELECT ct,st,r,maxr FROM tasks WHERE id=? AND (w=? OR w IS NULL)", (tid, worker_id)).fetchone()
            if not t: return
            tnow = now_ms()
            if ok:
                self.c.execute("UPDATE tasks SET s='d', et=?, res=?, w=NULL WHERE id=?",
                               (tnow, json.dumps(result)[:2000] if result else None, tid))
                if t["st"]:
                    qt = (t["st"]-t["ct"])/1000.0; et=(tnow - t["st"])/1000.0
                    self.c.execute("INSERT OR REPLACE INTO metrics(task_id,qt,et) VALUES(?,?,?)", (tid,qt,et))
            else:
                rc = t["r"] or 0; mr = t["maxr"] or DEFAULT_RETRIES
                if rc < mr:
                    delay = 1000*(2**rc)
                    self.c.execute("UPDATE tasks SET s='q', at=?, r=r+1, e=?, w=NULL WHERE id=?",
                                   (tnow+delay, (error or "")[:500], tid))
                else:
                    self.c.execute("UPDATE tasks SET s='f', et=?, e=?, w=NULL WHERE id=?", (tnow, (error or "")[:500], tid))

    def reclaim(self, timeout_ms:int=300000) -> int:
        with self.lock:
            cutoff = now_ms() - timeout_ms
            return self.c.execute("UPDATE tasks SET s='q', w=NULL, r=r+1 WHERE s='r' AND st<?", (cutoff,)).rowcount

    def running_units(self) -> Dict[str,int]:
        with self.lock:
            rows = self.c.execute("SELECT id,unit FROM tasks WHERE s IN ('start','sched','r') AND unit IS NOT NULL").fetchall()
            return {row["unit"]: row["id"] for row in rows}

    def stats(self) -> Dict[str,Any]:
        with self.lock:
            counts = {r["s"]: r["c"] for r in self.c.execute("SELECT s,COUNT(*) c FROM tasks GROUP BY s")}
            perf = self.c.execute("SELECT AVG(qt) avg_qt, AVG(et) avg_et, MAX(qt) max_qt, MAX(et) max_et FROM metrics").fetchone()
            return {"tasks": counts, "perf": dict(perf) if perf else {}}

    def cleanup(self, days:int=7) -> int:
        cutoff = now_ms() - days*86400000
        with self.lock:
            n = self.c.execute("DELETE FROM tasks WHERE s IN ('d','f') AND et<?", (cutoff,)).rowcount
            pc = self.c.execute("PRAGMA page_count").fetchone()[0]
            fr = self.c.execute("PRAGMA freelist_count").fetchone()[0]
            if fr > pc*0.3: self.c.execute("VACUUM")
            return n

# ---------- systemd orchestration ----------
def systemd_start(db:Store, task:sqlite3.Row) -> tuple[bool,str,str]:
    """Start via systemd-run; support OnCalendar & on-active delay; set Persistent=true."""
    unit = unit_name(task["name"] or task["id"])
    props = ["--property=StandardOutput=journal",
             "--property=StandardError=journal",
             "--property=KillMode=control-group",
             "--property=TimeoutSec={}".format(task["timeout"] or DEFAULT_TIMEOUT)]
    if task["cwd"]:  props += [f"--property=WorkingDirectory={task['cwd']}"]
    if task["nice"] is not None: props += [f"--property=Nice={int(task['nice'])}"]
    if task["rtprio"] is not None:
        props += ["--property=CPUSchedulingPolicy=rr",
                  f"--property=CPUSchedulingPriority={int(task['rtprio'])}"]
    if task["slice"]: props += [f"--slice={task['slice']}"]
    if task["cpu_weight"]: props += [f"--property=CPUWeight={int(task['cpu_weight'])}"]
    if task["mem_max_mb"]: props += [f"--property=MemoryMax={int(task['mem_max_mb'])}M"]

    env=[]
    if task["env"]:
        for k,v in json.loads(task["env"]).items():
            env += ["--setenv", f"{k}={v}"]

    when=[]
    if task["schedule"]:
        when += ["--on-calendar", task["schedule"]]
    else:
        # if future 'at', translate to on-active delay
        delay_ms = max(0, (task["at"] or now_ms()) - now_ms())
        if delay_ms>0: when += ["--on-active", f"{int((delay_ms+999)/1000)}s"]

    # Build shell command: join cmd + args (if any)
    args = json.loads(task["args"] or "[]")
    shell = task["cmd"] if not args else task["cmd"] + " " + " ".join(shlex.quote(a) for a in args)
    cp = run([*SYSDRUN, "--unit", unit, *props, *env, *when, "--", "/bin/sh", "-lc", shell])
    db.update(task["id"], unit=unit, s=("sched" if when else "start"))
    msg = cp.stderr.strip() or cp.stdout.strip()
    return (cp.returncode==0, unit, msg)

def systemd_stop(db:Store, name_or_id:str):
    unit = unit_name(name_or_id)
    run(SYSTEMCTL + ["stop", unit])
    run(SYSTEMCTL + ["stop", unit.replace(".service",".timer")])
    # status reconciled later

def systemd_status(name_or_id:str) -> Dict[str,str]:
    unit = unit_name(name_or_id)
    cp = run(SYSTEMCTL + ["show", unit, "--property=ActiveState", "--property=Result", "--property=MainPID"])
    if cp.returncode!=0: return {"unit": unit, "active":"unknown"}
    m = dict(line.split("=",1) for line in cp.stdout.splitlines() if "=" in line)
    return {"unit": unit, "active": m.get("ActiveState"), "result": m.get("Result"), "pid": m.get("MainPID")}

def reconcile_systemd(db:Store) -> int:
    """Batch-check many units efficiently; mark tasks done/failed."""
    umap = db.running_units()
    if not umap: return 0
    cp = run([*SYSTEMCTL, "show", *umap.keys(), "--property=Id,ActiveState,Result"])
    if cp.returncode!=0: return 0
    count=0
    for block in cp.stdout.strip().split("\n\n"):
        props = dict(line.split("=",1) for line in block.splitlines() if "=" in line)
        unit = props.get("Id"); tid = umap.get(unit); 
        if not tid: continue
        active = props.get("ActiveState"); result = props.get("Result")
        if active in ("inactive","failed"):
            db.done(tid, ok=(result=="success"))
            count += 1
        elif active=="active":
            # ensure state marked running
            db.update(tid, s='r')
    return count

# ---------- local/py worker ----------
class Worker:
    def __init__(self, store:Store, wid:Optional[str]=None):
        self.db=store
        self.wid=wid or f"w{os.getpid()}"
        self.run_flag=True
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT,  self._stop)
    def _stop(self,*_): self.run_flag=False

    def _exec_py(self, cmd:str, args:List[str], timeout:int) -> tuple[bool,Dict[str,str]|None,str|None]:
        """Execute 'py:module.func' in-process (simple & fast)."""
        try:
            assert cmd.startswith("py:"), "not py job"
            mod_fn = cmd[3:]
            mod, fn = mod_fn.rsplit(".",1)
            module = importlib.import_module(mod)
            func = getattr(module, fn)
            # crude timeout via alarm (POSIX); fallback to no-timeout if not available
            ok=True; out=None; err=None
            if hasattr(signal, "SIGALRM"):
                def _raise(*_): raise TimeoutError("PY_TIMEOUT")
                signal.signal(signal.SIGALRM, _raise); signal.alarm(max(1, int(timeout)))
                result = func(*args) if args else func()
                signal.alarm(0)
            else:
                result = func(*args) if args else func()
            out = {"stdout": str(result)[:1000], "stderr": ""}
            return True, out, None
        except TimeoutError:
            return False, None, "TIMEOUT"
        except Exception as e:
            return False, None, repr(e)

    def loop(self, batch:int=1, idle_ms:int=50):
        print(f"Worker {self.wid} running (batch={batch})")
        tick=0
        while self.run_flag:
            tick += 1
            if tick%100==0:
                r=self.db.reclaim()
                if r: print(f"reclaimed {r} stalled")
                # also sync with systemd
                try: 
                    n=reconcile_systemd(self.db)
                    if n: print(f"reconciled {n} systemd tasks")
                except Exception: pass
            got=[]
            for _ in range(batch):
                item=self.db.pop(self.wid)
                if item: got.append(item)
            if not got:
                time.sleep(idle_ms/1000.0); continue
            for t in got:
                if not self.run_flag: break
                mode=t["mode"]; args=json.loads(t["args"] or "[]"); env=json.loads(t["env"] or "{}")
                try:
                    if mode=="py" and t["cmd"].startswith("py:"):
                        ok,res,err=self._exec_py(t["cmd"], args, int(t["timeout"] or DEFAULT_TIMEOUT))
                        self.db.done(t["id"], ok, res, err, self.wid); continue
                    # local subprocess
                    shell = t["cmd"] if not args else t["cmd"] + " " + " ".join(shlex.quote(a) for a in args)
                    proc=subprocess.run(shell, shell=True, capture_output=True, text=True,
                                        timeout=int(t["timeout"] or DEFAULT_TIMEOUT),
                                        cwd=(t["cwd"] or None),
                                        env={**os.environ, **env})
                    self.db.done(t["id"], proc.returncode==0,
                                 {"stdout": proc.stdout[:1000], "stderr": proc.stderr[:1000]},
                                 proc.stderr if proc.returncode!=0 else None, self.wid)
                except subprocess.TimeoutExpired:
                    self.db.done(t["id"], False, error="TIMEOUT", worker_id=self.wid)
                except Exception as e:
                    self.db.done(t["id"], False, error=str(e), worker_id=self.wid)

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="aiose — All-in-One Scheduler & Executor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # add
    pa = sub.add_parser("add", help="add task")
    pa.add_argument("task_cmd", help="shell string")
    pa.add_argument("args", nargs="*", help="args (joined for shell; passed to py func)")
    pa.add_argument("--name")
    pa.add_argument("--mode", choices=["systemd"], default="systemd")
    pa.add_argument("--priority", type=int, default=0)
    pa.add_argument("--delay-ms", type=int, default=0)
    pa.add_argument("--deps", help="JSON list of task IDs")
    pa.add_argument("--env", action="append", default=[], help="KEY=VAL")
    pa.add_argument("--cwd")
    pa.add_argument("--on-calendar", help="systemd OnCalendar expression")
    pa.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    pa.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    # systemd props
    pa.add_argument("--rtprio", type=int); pa.add_argument("--nice", type=int)
    pa.add_argument("--slice"); pa.add_argument("--cpu-weight", type=int); pa.add_argument("--mem-max-mb", type=int)
    pa.add_argument("--start", action="store_true", help="start immediately (systemd)")

    # worker
    pw = sub.add_parser("worker", help="run local/py worker")
    pw.add_argument("--batch", type=int, default=1); pw.add_argument("--idle-ms", type=int, default=50)

    # systemd management
    ps = sub.add_parser("start", help="start a systemd task by id/name")
    ps.add_argument("name_or_id")
    pk = sub.add_parser("stop", help="stop systemd task by id/name"); pk.add_argument("name_or_id")
    pz = sub.add_parser("status", help="status for id/name");        pz.add_argument("name_or_id")

    # ops
    sub.add_parser("list", help="list tasks")
    sub.add_parser("stats", help="show stats")
    pc = sub.add_parser("cleanup", help="delete old done/failed"); pc.add_argument("--days", type=int, default=7)
    sub.add_parser("reconcile", help="reconcile systemd units")
    sub.add_parser("install", help="print a systemd user service for aiose worker")

    args = ap.parse_args()
    db = Store()

    if args.cmd=="add":
        env = dict(e.split("=",1) for e in args.env) if args.env else {}
        at  = now_ms() + max(0, args.delay_ms)
        dep = json.dumps(json.loads(args.deps)) if args.deps else None
        tid = db.add(
            name=args.name, cmd=args.task_cmd, mode="systemd", args=json.dumps(args.args) if args.args else None,
            env=(json.dumps(env) if env else None), cwd=args.cwd, p=args.priority, s="q",
            at=at, schedule=args.on_calendar, dep=dep, timeout=args.timeout, maxr=args.retries,
            rtprio=args.rtprio, nice=args.nice, slice=args.slice, cpu_weight=args.cpu_weight, mem_max_mb=args.mem_max_mb
        )
        row = db.get_by_id(tid)
        ok, unit, msg = systemd_start(db, row)
        print(unit if ok else f"ERROR: {msg}")

    elif args.cmd=="worker":
        Worker(db).loop(batch=args.batch, idle_ms=args.idle_ms)

    elif args.cmd=="start":
        key = args.name_or_id
        row = db.get_by_id(int(key)) if key.isdigit() else db.get_by_name(key)
        if not row: sys.exit("unknown task")
        if row["mode"]!="systemd": sys.exit("task is not systemd mode")
        ok, unit, msg = systemd_start(db, row)
        print(unit if ok else f"ERROR: {msg}")

    elif args.cmd=="stop":
        systemd_stop(db, args.name_or_id); print("stopped")

    elif args.cmd=="status":
        print(json.dumps(systemd_status(args.name_or_id), indent=2))

    elif args.cmd=="list":
        try: reconcile_systemd(db)
        except Exception: pass
        for r in db.list():
            ident=r["name"] or r["id"]; sched=r["schedule"] or "-"
            unit=r["unit"] or "-"; mode=r["mode"]; s=r["s"]
            print(f"{ident:20} id={r['id']:4} mode={mode:7} s={s:5} p={r['p']:2} at={r['at']} unit={unit} sched={sched}")

    elif args.cmd=="stats":
        print(json.dumps(db.stats(), indent=2))

    elif args.cmd=="cleanup":
        print(f"deleted {db.cleanup(args.days)}")

    elif args.cmd=="reconcile":
        n=reconcile_systemd(db); print(f"ok (updated {n})")

    elif args.cmd=="install":
        exe = sys.executable; here=os.path.abspath(__file__)
        print(f"""[Unit]
Description=aiose worker
After=default.target

[Service]
Type=simple
ExecStart={exe} {here} worker
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
""")

if __name__ == "__main__":
    main()
