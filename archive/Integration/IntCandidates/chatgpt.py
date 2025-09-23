#!/usr/bin/env python3
"""
AIOS Orchestrator — unified, <500 lines
- Single SQLite DB for queue + orchestration metadata
- Two run modes:
  * local: fast in-process worker executes shell cmds with retries/backoff
  * systemd: isolation via transient user units (systemd-run), optional timers
- Dependencies, priorities, scheduling (at/on-calendar), metrics, cleanup
- Simple CLI: add | worker | start | stop | list | status | stats | reconcile | cleanup
"""
import argparse, json, os, shlex, signal, sqlite3, subprocess, sys, time, threading
from pathlib import Path
from typing import Optional, Dict, Any

# ---------- constants ----------
DB_PATH = Path.home() / ".aios_orchestrator.db"
UNIT_PREFIX = "aios-"
SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN   = ["systemd-run", "--user", "--collect", "--quiet"]

PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=268435456",
    "PRAGMA busy_timeout=5000",
    "PRAGMA wal_autocheckpoint=1000",
]

# ---------- helpers ----------
def now_ms() -> int: return int(time.time() * 1000)
def unit_name(name_or_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-:" else "_" for c in str(name_or_id))
    return f"{UNIT_PREFIX}{safe}.service"
def run(cmd:list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True)

# ---------- storage ----------
class Store:
    """SQLite with production pragmas; unified 'tasks' table for both modes."""
    def __init__(self, path=DB_PATH):
        self.c = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        for p in PRAGMAS: self.c.execute(p)
        self.c.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(
          id INTEGER PRIMARY KEY,
          name TEXT UNIQUE,                -- optional human handle
          cmd  TEXT NOT NULL,              -- shell command
          mode TEXT DEFAULT 'local',       -- 'local' | 'systemd'
          p INT DEFAULT 0,                 -- priority
          s TEXT DEFAULT 'q',              -- q=queued r=running d=done f=failed sched=scheduled start=started
          at INT DEFAULT 0,                -- scheduled_at (ms) for local
          w  TEXT,                         -- worker_id (local)
          r  INT DEFAULT 0,                -- retry_count (local)
          e  TEXT,                         -- error_message
          res TEXT,                        -- result (truncated stdout/stderr, local)
          ct INT DEFAULT (strftime('%s','now')*1000),
          st INT,                          -- started_at
          et INT,                          -- ended_at
          dep TEXT,                        -- JSON array of dependency IDs (local)
          -- Orchestration extras
          env TEXT, cwd TEXT, schedule TEXT,
          rtprio INTEGER, nice INTEGER, slice TEXT,
          cpu_weight INTEGER, mem_max_mb INTEGER,
          unit TEXT                        -- systemd unit name if used
        );
        CREATE INDEX IF NOT EXISTS idx_q ON tasks(s, p DESC, at, id) WHERE s IN ('q','r');
        CREATE TABLE IF NOT EXISTS metrics(task_id INTEGER PRIMARY KEY, qt REAL, et REAL,
            FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE);
        """)
    # ---- CRUD / queries ----
    def add(self, **kw) -> int:
        with self.lock:
            cols = ",".join(kw.keys()); qs = ",".join("?" for _ in kw)
            return self.c.execute(f"INSERT INTO tasks({cols}) VALUES({qs})", tuple(kw.values())).lastrowid
    def get_by_name(self, name:str) -> Optional[sqlite3.Row]:
        with self.lock: return self.c.execute("SELECT * FROM tasks WHERE name=?", (name,)).fetchone()
    def get_by_id(self, tid:int) -> Optional[sqlite3.Row]:
        with self.lock: return self.c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    def list(self) -> list[sqlite3.Row]:
        with self.lock: return self.c.execute("SELECT * FROM tasks ORDER BY ct DESC").fetchall()
    def update(self, tid:int, **kw):
        if not kw: return
        with self.lock:
            sets = ",".join(f"{k}=?" for k in kw)
            self.c.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*kw.values(), tid))
    # ---- queue ops (local) ----
    def pop(self, worker_id:str) -> Optional[Dict[str,Any]]:
        with self.lock:
            row = self.c.execute("""
              SELECT id, cmd FROM tasks
              WHERE mode='local' AND s='q' AND at<=?
                AND (dep IS NULL OR NOT EXISTS(
                    SELECT 1 FROM json_each(tasks.dep) d
                    JOIN tasks t2 ON t2.id = d.value
                    WHERE t2.s != 'd'
                ))
              ORDER BY p DESC, at, id
              LIMIT 1
            """, (now_ms(),)).fetchone()
            if not row: return None
            try:
                claimed = self.c.execute(
                    "UPDATE tasks SET s='r', w=?, st=? WHERE id=? AND s='q' RETURNING id, cmd",
                    (worker_id, now_ms(), row["id"])
                ).fetchone()
                if claimed: return {"id": claimed["id"], "cmd": claimed["cmd"]}
            except sqlite3.OperationalError:
                self.c.execute("BEGIN IMMEDIATE")
                n = self.c.execute("UPDATE tasks SET s='r', w=?, st=? WHERE id=? AND s='q'",
                                   (worker_id, now_ms(), row["id"])).rowcount
                self.c.execute("COMMIT")
                if n: return {"id": row["id"], "cmd": row["cmd"]}
        return None
    def done(self, tid:int, ok:bool, result:Any=None, error:str=None, worker_id:str=""):
        with self.lock:
            t = self.c.execute("SELECT ct, st FROM tasks WHERE id=? AND (w=? OR w IS NULL)", (tid, worker_id)).fetchone()
            if not t: return
            tnow = now_ms()
            if ok:
                self.c.execute("UPDATE tasks SET s='d', et=?, res=?, w=NULL WHERE id=?",
                               (tnow, json.dumps(result)[:2000] if result else None, tid))
                if t["st"]:
                    qt = (t["st"] - t["ct"]) / 1000.0; et = (tnow - t["st"]) / 1000.0
                    self.c.execute("INSERT OR REPLACE INTO metrics(task_id,qt,et) VALUES(?,?,?)", (tid, qt, et))
            else:
                row = self.c.execute("SELECT r FROM tasks WHERE id=?", (tid,)).fetchone()
                rc = (row["r"] if row else 0)
                if rc < 3:
                    delay = 1000 * (2 ** rc)
                    self.c.execute("UPDATE tasks SET s='q', at=?, r=r+1, e=?, w=NULL WHERE id=?",
                                   (now_ms()+delay, error, tid))
                else:
                    self.c.execute("UPDATE tasks SET s='f', et=?, e=?, w=NULL WHERE id=?", (tnow, error, tid))
    def reclaim(self, timeout_ms:int=300000) -> int:
        with self.lock:
            cutoff = now_ms() - timeout_ms
            return self.c.execute("UPDATE tasks SET s='q', w=NULL, r=r+1 WHERE s='r' AND st < ?", (cutoff,)).rowcount
    def stats(self) -> Dict[str,Any]:
        with self.lock:
            counts = {r["s"]: r["c"] for r in self.c.execute("SELECT s, COUNT(*) c FROM tasks GROUP BY s")}
            perf = self.c.execute("SELECT AVG(qt) avg_qt, AVG(et) avg_et, MAX(qt) max_qt, MAX(et) max_et FROM metrics").fetchone()
            wal = self.c.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            return {"tasks": counts, "perf": dict(perf) if perf else {}, "wal_pages": wal[1] if wal else 0}
    def cleanup(self, days:int=7) -> int:
        cutoff = now_ms() - days*86400000
        with self.lock:
            n = self.c.execute("DELETE FROM tasks WHERE s IN ('d','f') AND et < ?", (cutoff,)).rowcount
            pc = self.c.execute("PRAGMA page_count").fetchone()[0]
            fr = self.c.execute("PRAGMA freelist_count").fetchone()[0]
            if fr > pc * 0.3: self.c.execute("VACUUM")
            return n

# ---------- systemd orchestration ----------
def systemd_start(store:Store, task:sqlite3.Row) -> tuple[bool,str,str]:
    unit = unit_name(task["name"] or task["id"])
    props = ["--property=StandardOutput=journal",
             "--property=StandardError=journal",
             "--property=KillMode=control-group"]
    if task["cwd"]:  props += [f"--property=WorkingDirectory={task['cwd']}"]
    if task["nice"] is not None: props += [f"--property=Nice={int(task['nice'])}"]
    if task["rtprio"] is not None:
        props += ["--property=CPUSchedulingPolicy=rr",
                  f"--property=CPUSchedulingPriority={int(task['rtprio'])}"]
    if task["slice"]: props += [f"--slice={task['slice']}"]
    if task["cpu_weight"]: props += [f"--property=CPUWeight={int(task['cpu_weight'])}"]
    if task["mem_max_mb"]: props += [f"--property=MemoryMax={int(task['mem_max_mb'])}M"]
    env = []
    if task["env"]:
        for k,v in json.loads(task["env"]).items():
            env += ["--setenv", f"{k}={v}"]
    when = []
    if task["schedule"]: when += ["--on-calendar", task["schedule"]]
    cmd = [*SYSDRUN, "--unit", unit, *props, *env, *when, "--", "/bin/sh", "-lc", task["cmd"]]
    cp = run(cmd)
    store.update(task["id"], unit=unit, s=("sched" if task["schedule"] else "start"))
    msg = cp.stderr.strip() or cp.stdout.strip()
    return (cp.returncode==0, unit, msg)

def systemd_stop(store:Store, name_or_id:str):
    unit = unit_name(name_or_id)
    run(SYSTEMCTL + ["stop", unit])
    run(SYSTEMCTL + ["stop", unit.replace(".service",".timer")])
    # status will be reconciled later

def systemd_status(name_or_id:str) -> Dict[str,str]:
    unit = unit_name(name_or_id)
    cp = run(SYSTEMCTL + ["show", unit, "--property=ActiveState", "--property=Result", "--property=MainPID"])
    if cp.returncode != 0: return {"unit": unit, "active": "unknown"}
    m = {}
    for line in cp.stdout.splitlines():
        if "=" in line:
            k,v = line.split("=",1); m[k]=v
    return {"unit": unit, "active": m.get("ActiveState"), "result": m.get("Result"), "pid": m.get("MainPID")}

def reconcile_systemd(store:Store):
    rows = store.list()
    for r in rows:
        if r["mode"]!="systemd" or not r["unit"]: continue
        cp = run(SYSTEMCTL + ["show", r["unit"], "--property=ActiveState", "--property=Result"])
        if cp.returncode!=0: continue
        m = dict(x.split("=",1) for x in cp.stdout.splitlines() if "=" in x)
        active, result = m.get("ActiveState"), m.get("Result")
        if active in ("inactive","failed"):
            store.update(r["id"], s=("d" if result=="success" else "f"), et=now_ms())

# ---------- local worker ----------
class Worker:
    def __init__(self, store:Store, wid:Optional[str]=None):
        self.db = store
        self.wid = wid or f"w{os.getpid()}"
        self.run_flag = True
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT,  self._stop)
    def _stop(self, *_): self.run_flag = False
    def loop(self, batch:int=1, idle_ms:int=50, timeout_s:int=290):
        print(f"Worker {self.wid} running (batch={batch})")
        tick = 0
        while self.run_flag:
            tick += 1
            if tick % 100 == 0:
                r = self.db.reclaim()
                if r: print(f"reclaimed {r} stalled")
            got = []
            for _ in range(batch):
                item = self.db.pop(self.wid)
                if item: got.append(item)
            if not got:
                time.sleep(idle_ms/1000.0); continue
            for t in got:
                if not self.run_flag: break
                try:
                    proc = subprocess.run(t["cmd"], shell=True, capture_output=True, text=True, timeout=timeout_s)
                    ok = (proc.returncode==0)
                    self.db.done(t["id"], ok,
                                 result={"stdout": proc.stdout[:1000], "stderr": proc.stderr[:1000]},
                                 error=(proc.stderr if not ok else None),
                                 worker_id=self.wid)
                except subprocess.TimeoutExpired:
                    self.db.done(t["id"], False, error="TIMEOUT", worker_id=self.wid)
                except Exception as e:
                    self.db.done(t["id"], False, error=str(e), worker_id=self.wid)

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="AIOS unified orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # add task (works for both modes)
    pa = sub.add_parser("add", help="add task (local default)"); 
    pa.add_argument("cmd"); pa.add_argument("args", nargs="*")
    pa.add_argument("--name")
    pa.add_argument("--mode", choices=["local","systemd"], default="local")
    pa.add_argument("--priority", type=int, default=0)
    pa.add_argument("--delay-ms", type=int, default=0, help="for local 'at'")
    pa.add_argument("--deps", help="JSON list of task IDs (local)")
    pa.add_argument("--env", action="append", default=[], help="KEY=VAL")
    pa.add_argument("--cwd")
    pa.add_argument("--on-calendar", help="systemd OnCalendar (systemd mode)")
    pa.add_argument("--rtprio", type=int)
    pa.add_argument("--nice", type=int)
    pa.add_argument("--slice")
    pa.add_argument("--cpu-weight", type=int)
    pa.add_argument("--mem-max-mb", type=int)
    pa.add_argument("--start", action="store_true", help="start now (systemd mode)")

    # worker
    pw = sub.add_parser("worker", help="run local worker")
    pw.add_argument("--batch", type=int, default=1)
    pw.add_argument("--idle-ms", type=int, default=50)
    pw.add_argument("--timeout-s", type=int, default=290)

    # start/stop/status for named/id (systemd preferred)
    ps = sub.add_parser("start", help="start systemd task by name/id"); ps.add_argument("name_or_id")
    pk = sub.add_parser("stop",  help="stop systemd task by name/id");  pk.add_argument("name_or_id")
    pz = sub.add_parser("status",help="status by name/id");             pz.add_argument("name_or_id")

    # list/stats/cleanup/reconcile
    sub.add_parser("list", help="list tasks")
    sub.add_parser("stats", help="aggregate stats")
    pc = sub.add_parser("cleanup", help="delete old done/failed"); pc.add_argument("--days", type=int, default=7)
    sub.add_parser("reconcile", help="refresh systemd task statuses")

    args = ap.parse_args()
    db = Store()

    if args.cmd == "add":
        env = dict(e.split("=",1) for e in args.env) if args.env else {}
        cmd = args.cmd + (" " + " ".join(shlex.quote(a) for a in args.args) if args.args else "")
        at = (now_ms() + args.delay_ms) if args.mode=="local" and args.delay_ms>0 else now_ms()
        dep = args.deps if not args.deps else json.dumps(json.loads(args.deps))
        tid = db.add(
            name=args.name, cmd=cmd, mode=args.mode, p=args.priority, s=("q" if args.mode=="local" else "q"),
            at=at, dep=dep, env=(json.dumps(env) if env else None), cwd=args.cwd,
            schedule=args.on_calendar, rtprio=args.rtprio, nice=args.nice, slice=args.slice,
            cpu_weight=args.cpu_weight, mem_max_mb=args.mem_max_mb
        )
        if args.mode=="systemd" and (args.start or args.on_calendar):
            row = db.get_by_id(tid)
            ok, unit, msg = systemd_start(db, row)
            print(unit if ok else f"ERROR: {msg}")
        else:
            print(f"queued task {tid}")

    elif args.cmd == "worker":
        Worker(db).loop(batch=args.batch, idle_ms=args.idle_ms, timeout_s=args.timeout_s)

    elif args.cmd == "start":
        # allow numeric id or name
        row = db.get_by_id(int(args.name_or_id)) if args.name_or_id.isdigit() else db.get_by_name(args.name_or_id)
        if not row: sys.exit("unknown task")
        if row["mode"]!="systemd": sys.exit("task is not systemd mode")
        ok, unit, msg = systemd_start(db, row)
        print(unit if ok else f"ERROR: {msg}")

    elif args.cmd == "stop":
        systemd_stop(db, args.name_or_id); print("stopped")

    elif args.cmd == "status":
        st = systemd_status(args.name_or_id); print(json.dumps(st, indent=2))

    elif args.cmd == "list":
        reconcile_systemd(db)
        for r in db.list():
            ident = r["name"] or r["id"]
            sched = r["schedule"] or "-"
            unit  = r["unit"] or "-"
            print(f"{ident:20} id={r['id']:4} mode={r['mode']:7} s={r['s']:5} p={r['p']:2} at={r['at']} unit={unit} sched={sched}")

    elif args.cmd == "stats":
        print(json.dumps(db.stats(), indent=2))

    elif args.cmd == "cleanup":
        n = db.cleanup(args.days); print(f"deleted {n}")

    elif args.cmd == "reconcile":
        reconcile_systemd(db); print("ok")

if __name__ == "__main__":
    main()
