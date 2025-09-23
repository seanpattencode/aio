#!/usr/bin/env python3
# aios_sqlite_queue.py  —  SQLite-backed queue for AIOS + systemd
# Public domain / CC0-style: use freely.

import argparse, sqlite3, time, json, os, sys, signal, threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import subprocess

# ---- Orchestrator import (expects the class defined in the same runtime/file) ----
try:
    SystemdOrchestrator  # type: ignore
except NameError:
    # If run standalone with no orchestrator in scope, provide a minimal stub.
    class SystemdOrchestrator:
        def __init__(self): self.jobs = {}
        def _run(self,*a): return subprocess.run(["true"])
        def add_job(self,name,command,restart="no"):
            self.jobs[name] = f"aios-{name}.service"; return self.jobs[name]
        def start_job(self,name): return 0.0
        def status(self): return {}
        def _run(self,*args): pass

BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = str(BASE_DIR / "aios.sqlite3")

# ---- SQL schema ----
SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA temp_store=MEMORY;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  command TEXT NOT NULL,
  args_json TEXT DEFAULT '{}',
  priority INTEGER NOT NULL DEFAULT 0,
  unique_key TEXT,                -- for de-dup semantics
  not_before_ms INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'queued', -- queued|leased|running|succeeded|failed|canceled
  lease_until_ms INTEGER,         -- when another worker may reclaim
  worker_id TEXT,                 -- who leased / runs it
  unit_name TEXT,                 -- systemd unit name when running
  run_attempts INTEGER NOT NULL DEFAULT 0,
  max_retries INTEGER NOT NULL DEFAULT 3,
  backoff_ms INTEGER NOT NULL DEFAULT 60000,
  created_ms INTEGER NOT NULL,
  updated_ms INTEGER NOT NULL,
  tags TEXT DEFAULT ''            -- comma-separated
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_unique_key
  ON tasks(unique_key) WHERE unique_key IS NOT NULL AND state IN ('queued','leased','running');

CREATE INDEX IF NOT EXISTS idx_tasks_ready
  ON tasks(state, priority DESC, not_before_ms, id);

CREATE TABLE IF NOT EXISTS task_dep (
  parent_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  child_id  INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  PRIMARY KEY (parent_id, child_id)
);

CREATE TABLE IF NOT EXISTS task_run (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  start_ms INTEGER NOT NULL,
  end_ms   INTEGER,
  exit_code INTEGER,
  status TEXT,              -- running|succeeded|failed
  note TEXT DEFAULT ''
);

-- A tiny migration/versioning marker
INSERT OR IGNORE INTO meta(key,value) VALUES ('schema_version','1');
"""

@dataclass
class Task:
    id: int
    name: str
    command: str
    args_json: str
    priority: int
    unique_key: Optional[str]
    not_before_ms: int
    state: str
    lease_until_ms: Optional[int]
    worker_id: Optional[str]
    unit_name: Optional[str]
    run_attempts: int
    max_retries: int
    backoff_ms: int
    created_ms: int
    updated_ms: int
    tags: str

def _now_ms() -> int:
    return int(time.time() * 1000)

class AiosQueue:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self._conn:
            for stmt in [s.strip() for s in SCHEMA.split(";\n") if s.strip()]:
                self._conn.execute(stmt)

    # ---- Enqueue API ----
    def enqueue(self, name: str, command: str, *, args: Dict = None,
                priority: int = 0, not_before_ms: int = 0,
                unique_key: Optional[str] = None, max_retries: int = 3,
                backoff_ms: int = 60_000, tags: List[str] = None) -> int:
        args = args or {}
        tags_str = ",".join(tags) if tags else ""
        now = _now_ms()
        with self._conn:
            if unique_key:
                # If an equivalent job exists and is pending/running, do nothing.
                cur = self._conn.execute(
                    "SELECT id FROM tasks WHERE unique_key=? AND state IN ('queued','leased','running')",
                    (unique_key,))
                if cur.fetchone():
                    return cur.fetchone() or -1
            cur = self._conn.execute("""
                INSERT INTO tasks (name,command,args_json,priority,unique_key,not_before_ms,state,
                                   lease_until_ms,worker_id,unit_name,run_attempts,max_retries,backoff_ms,
                                   created_ms,updated_ms,tags)
                VALUES (?,?,?,?,?,?, 'queued', NULL,NULL,NULL,0,?,?,?, ?,?)
            """, (name, command, json.dumps(args), priority, unique_key, not_before_ms,
                  max_retries, backoff_ms, now, now, tags_str))
            return cur.lastrowid

    def add_dependency(self, parent_id: int, child_id: int):
        with self._conn:
            self._conn.execute("INSERT OR IGNORE INTO task_dep(parent_id,child_id) VALUES(?,?)",
                               (parent_id, child_id))

    # ---- Leasing / claiming ----
    def _eligible_ids(self, limit: int) -> List[int]:
        # child tasks only run when all parents succeeded
        sql = """
        SELECT t.id
        FROM tasks t
        LEFT JOIN task_dep d ON d.child_id = t.id
        LEFT JOIN tasks p    ON p.id = d.parent_id
        WHERE t.state='queued'
          AND t.not_before_ms <= ?
          AND (p.id IS NULL OR (SELECT COUNT(1) FROM task_dep dd
                                JOIN tasks pp ON pp.id=dd.parent_id
                                WHERE dd.child_id=t.id AND pp.state='succeeded') =
                              (SELECT COUNT(1) FROM task_dep WHERE child_id=t.id))
        ORDER BY t.priority DESC, t.id ASC
        LIMIT ?;
        """
        cur = self._conn.execute(sql, (_now_ms(), limit))
        return [r[0] for r in cur.fetchall()]

    def claim(self, worker_id: str, limit: int = 1, lease_ms: int = 5*60_000) -> List[Task]:
        ids = self._eligible_ids(limit)
        claimed: List[Task] = []
        now = _now_ms()
        until = now + lease_ms
        with self._conn:
            for tid in ids:
                res = self._conn.execute("""
                    UPDATE tasks
                    SET state='leased', lease_until_ms=?, worker_id=?, updated_ms=?
                    WHERE id=? AND state='queued'
                """, (until, worker_id, now, tid))
                if res.rowcount == 1:
                    claimed.append(self.get_task(tid))
        return claimed

    def requeue_expired_leases(self) -> int:
        now = _now_ms()
        with self._conn:
            res = self._conn.execute("""
                UPDATE tasks
                SET state='queued', lease_until_ms=NULL, worker_id=NULL, updated_ms=?
                WHERE state='leased' AND lease_until_ms IS NOT NULL AND lease_until_ms < ?
            """, (now, now))
            return res.rowcount

    # ---- Running / completion ----
    def start_run(self, task_id: int, unit_name: str) -> int:
        now = _now_ms()
        with self._conn:
            self._conn.execute("""
                UPDATE tasks
                SET state='running', unit_name=?, run_attempts=run_attempts+1, updated_ms=?
                WHERE id=? AND state IN ('leased','queued')
            """, (unit_name, now, task_id))
            cur = self._conn.execute("""
                INSERT INTO task_run(task_id,start_ms,status) VALUES(?,?,'running')
            """, (task_id, now))
            return cur.lastrowid

    def complete_run(self, task_id: int, run_id: int, *, success: bool, exit_code: int, note: str = ""):
        now = _now_ms()
        new_state = 'succeeded' if success else 'failed'
        with self._conn:
            self._conn.execute("""
                UPDATE task_run SET end_ms=?, exit_code=?, status=? WHERE run_id=?
            """, (now, exit_code, new_state, run_id))
            self._conn.execute("""
                UPDATE tasks SET state=?, lease_until_ms=NULL, worker_id=NULL, updated_ms=?
                WHERE id=?
            """, (new_state, now, task_id))

    def maybe_backoff(self, task_id: int):
        # If failed and retries left, move back to queued with backoff.
        t = self.get_task(task_id)
        if t.state != 'failed': return
        if t.run_attempts < t.max_retries:
            delay = min(t.backoff_ms * max(1, t.run_attempts), 60*60*1000)  # cap 1h
            nb = _now_ms() + delay
            with self._conn:
                self._conn.execute("""
                    UPDATE tasks SET state='queued', not_before_ms=?, updated_ms=? WHERE id=?
                """, (nb, _now_ms(), task_id))

    def cancel(self, task_id: int):
        with self._conn:
            self._conn.execute("""
                UPDATE tasks SET state='canceled', updated_ms=? WHERE id=? AND state IN ('queued','leased')
            """, (_now_ms(), task_id))

    def get_task(self, task_id: int) -> Task:
        cur = self._conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        r = cur.fetchone()
        if not r: raise KeyError(task_id)
        return Task(**dict(r))

    def running(self) -> List[Task]:
        cur = self._conn.execute("SELECT * FROM tasks WHERE state='running'")
        return [Task(**dict(r)) for r in cur.fetchall()]

    def list(self, state: Optional[str] = None, limit: int = 50) -> List[Task]:
        q = "SELECT * FROM tasks"
        p: Tuple = ()
        if state:
            q += " WHERE state=?"
            p = (state,)
        q += " ORDER BY created_ms DESC LIMIT ?"
        p += (limit,)
        cur = self._conn.execute(q, p)
        return [Task(**dict(r)) for r in cur.fetchall()]

# ---- Worker that maps tasks -> systemd units via your orchestrator ----

class Worker:
    def __init__(self, queue: AiosQueue, worker_id: str = None, poll_ms: int = 1000):
        self.q = queue
        self.worker_id = worker_id or f"worker-{os.uname().nodename}-{os.getpid()}"
        self.poll_ms = poll_ms
        self.orch = SystemdOrchestrator()
        self._stop = threading.Event()

    def stop(self, *_):
        self._stop.set()

    def _unit_for(self, task_id: int) -> str:
        return f"task-{task_id}"

    def loop(self, parallel: int = 1, lease_ms: int = 10*60_000):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        print(f"[worker] {self.worker_id} starting; parallel={parallel}")
        while not self._stop.is_set():
            try:
                reclaimed = self.q.requeue_expired_leases()
                if reclaimed:
                    print(f"[worker] reclaimed {reclaimed} expired leases")
                # Claim new tasks
                claimed = self.q.claim(self.worker_id, limit=parallel, lease_ms=lease_ms)
                for t in claimed:
                    unit = self._unit_for(t.id)
                    # Create one-shot unit so completion is observable
                    self.orch.add_job(unit, t.command, restart="no")
                    self.orch.start_job(unit)
                    run_id = self.q.start_run(t.id, unit)
                    print(f"[worker] started task {t.id} -> {unit} (run {run_id})")

                # Reap running tasks by asking systemd
                self._reap_running()

                time.sleep(self.poll_ms / 1000.0)
            except Exception as e:
                print(f"[worker] error: {e}")
                time.sleep(1.0)

    def _reap_running(self):
        running = self.q.running()
        for t in running:
            # Query systemd for state/exit status
            result = subprocess.run(["systemctl", "--user", "show", t.unit_name or "",
                                     "--property=ActiveState,ExecMainStatus"],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                continue
            props = {}
            for line in result.stdout.strip().splitlines():
                if "=" in line:
                    k,v = line.split("=",1); props[k]=v
            active = props.get("ActiveState","")
            # If unit finished (dead/inactive), mark complete
            if active in ("inactive","failed","deactivating","maintenance"):
                exit_code = int(props.get("ExecMainStatus","0") or "0")
                success = (exit_code == 0)
                # Find the latest run row
                cur = self.q._conn.execute(
                    "SELECT run_id FROM task_run WHERE task_id=? ORDER BY run_id DESC LIMIT 1",(t.id,))
                row = cur.fetchone()
                run_id = row[0] if row else None
                if run_id is not None:
                    self.q.complete_run(t.id, run_id, success=success, exit_code=exit_code,
                                        note=f"unit={t.unit_name}")
                    if not success:
                        self.q.maybe_backoff(t.id)
                print(f"[worker] completed task {t.id} exit={exit_code}")

# ---- CLI ----

def cli():
    ap = argparse.ArgumentParser(description="AIOS SQLite Task Queue")
    sub = ap.add_subparsers(dest="cmd")

    sp = sub.add_parser("enqueue", help="enqueue a task")
    sp.add_argument("--name", required=True)
    sp.add_argument("--cmd", required=True)
    sp.add_argument("--args", default="{}")
    sp.add_argument("--priority", type=int, default=0)
    sp.add_argument("--not-before-ms", type=int, default=0)
    sp.add_argument("--unique-key")
    sp.add_argument("--max-retries", type=int, default=3)
    sp.add_argument("--backoff-ms", type=int, default=60000)
    sp.add_argument("--tags", default="")

    sub.add_parser("list", help="list tasks")
    sp2 = sub.add_parser("worker", help="run worker loop")
    sp2.add_argument("--parallel", type=int, default=1)
    sp2.add_argument("--lease-ms", type=int, default=10*60_000)
    sp2.add_argument("--poll-ms", type=int, default=1000)

    sp3 = sub.add_parser("cancel", help="cancel a queued/leased task")
    sp3.add_argument("--id", type=int, required=True)

    args = ap.parse_args()
    q = AiosQueue(DB_PATH)

    if args.cmd == "enqueue":
        tid = q.enqueue(
            name=args.name, command=args.cmd,
            args=json.loads(args.args), priority=args.priority,
            not_before_ms=args.not_before_ms, unique_key=args.unique_key,
            max_retries=args.max_retries, backoff_ms=args.backoff_ms,
            tags=[t for t in args.tags.split(",") if t]
        )
        print(tid if isinstance(tid,int) else -1)
        return

    if args.cmd == "list":
        tasks = q.list(limit=200)
        for t in tasks:
            print(json.dumps({
                "id": t.id, "name": t.name, "state": t.state,
                "priority": t.priority, "nb": t.not_before_ms,
                "attempts": t.run_attempts, "max": t.max_retries,
                "unit": t.unit_name
            }))
        return

    if args.cmd == "worker":
        w = Worker(q, poll_ms=args.poll_ms)
        w.loop(parallel=args.parallel, lease_ms=args.lease_ms)
        return

    if args.cmd == "cancel":
        q.cancel(args.id); print("ok"); return

    ap.print_help()

if __name__ == "__main__":
    cli()
