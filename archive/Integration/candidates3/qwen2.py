#!/usr/bin/env python3
"""
Orchestrator: High-Performance Job Queue + Systemd Integration (<500 lines)
Synthesizes the best patterns from all candidates into a minimal, robust system.
"""
import argparse, json, os, shlex, signal, sqlite3, subprocess, sys, time, threading
from pathlib import Path
from typing import Optional, Dict, Any

# --- Configuration & Constants ---
DB_PATH = Path.home() / ".orchestrator.db"
UNIT_PREFIX = "orch-"
SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"]

# Production-grade SQLite pragmas (claudeCodeD, chatgpt, geminiDeep)
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA busy_timeout=5000",
    "PRAGMA wal_autocheckpoint=1000",
]

def now_ms() -> int:
    return int(time.time() * 1000)

def unit_name(name: str) -> str:
    """Generate a safe systemd unit name."""
    safe = "".join(c if c.isalnum() or c in "._-:" else "_" for c in name)
    return f"{UNIT_PREFIX}{safe}.service"

# --- Core Storage Engine ---
class Store:
    """High-performance, thread-safe SQLite storage with atomic operations."""
    def __init__(self, path=DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        
        # Apply performance optimizations
        for pragma in PRAGMAS:
            self.conn.execute(pragma)
        
        # Unified, minimal schema (Synthesized from chatgpt, geminiDeep, grok)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                cmd TEXT NOT NULL,
                args TEXT DEFAULT '[]',
                env TEXT,
                cwd TEXT,
                p INT DEFAULT 0,        -- priority
                s TEXT DEFAULT 'q',     -- status: q=queued, r=running, d=done, f=failed
                at INT DEFAULT 0,       -- scheduled_at (ms)
                w TEXT,                 -- worker_id
                r INT DEFAULT 0,        -- retry_count
                e TEXT,                 -- error_message
                res TEXT,               -- result
                ct INT DEFAULT (strftime('%s','now')*1000), -- created_at
                st INT, et INT,         -- started_at, ended_at
                dep TEXT,               -- JSON array of dependency IDs
                schedule TEXT,          -- systemd calendar format
                rtprio INTEGER,
                nice INTEGER,
                slice TEXT,
                cpu_weight INTEGER,
                mem_max_mb INTEGER,
                unit TEXT               -- systemd unit name
            );
            -- Optimized composite index for fetching (claudeCodeD pattern)
            CREATE INDEX IF NOT EXISTS idx_fetch ON tasks(s, p DESC, at, id) WHERE s = 'q';
            -- Metrics table (Chrome pattern from claudeCodeD)
            CREATE TABLE IF NOT EXISTS metrics (
                task_id INTEGER PRIMARY KEY,
                qt REAL,  -- queue_time (seconds)
                et REAL,  -- exec_time (seconds)
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
        """)

    # --- Atomic Queue Operations ---
    def pop(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Atomically claim the next eligible task, respecting dependencies and schedule."""
        now = now_ms()
        query = """
            SELECT id, cmd, args, env, cwd, rtprio, nice, slice, cpu_weight, mem_max_mb, schedule
            FROM tasks t
            WHERE s='q' AND at<=:now
            AND (dep IS NULL OR NOT EXISTS (
                SELECT 1 FROM json_each(t.dep) AS d
                JOIN tasks AS dt ON dt.id = d.value
                WHERE dt.s != 'd'
            ))
            ORDER BY p DESC, at, id
            LIMIT 1
        """
        with self.lock:
            row = self.conn.execute(query, {'now': now}).fetchone()
            if not row:
                return None

            # Atomically claim using UPDATE...RETURNING
            try:
                claimed = self.conn.execute("""
                    UPDATE tasks SET s='r', w=?, st=? 
                    WHERE id=? AND s='q' 
                    RETURNING id, cmd, args, env, cwd, rtprio, nice, slice, cpu_weight, mem_max_mb, schedule
                """, (worker_id, now, row['id'])).fetchone()
                if claimed:
                    task = dict(claimed)
                    for key in ['args', 'env']:
                        if task[key]:
                            task[key] = json.loads(task[key])
                    return task
            except sqlite3.OperationalError:
                # Fallback for older SQLite versions
                self.conn.execute("BEGIN IMMEDIATE")
                updated = self.conn.execute(
                    "UPDATE tasks SET s='r', w=?, st=? WHERE id=? AND s='q'",
                    (worker_id, now, row['id'])
                ).rowcount
                self.conn.execute("COMMIT")
                if updated:
                    task = dict(row)
                    for key in ['args', 'env']:
                        if task[key]:
                            task[key] = json.loads(task[key])
                    return task
        return None

    def finalize(self, task_id: int, success: bool, error: str = None):
        """Mark task as complete (d/f) or schedule retry (q), and record metrics."""
        now = now_ms()
        with self.lock:
            task = self.conn.execute("SELECT r, ct, st, unit FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task:
                return

            if success:
                self.conn.execute("UPDATE tasks SET s='d', et=?, unit=NULL WHERE id=?", (now, task_id))
                # Record performance metrics
                if task['st'] and task['ct']:
                    queue_time = (task['st'] - task['ct']) / 1000.0
                    exec_time = (now - task['st']) / 1000.0
                    self.conn.execute(
                        "INSERT OR REPLACE INTO metrics(task_id, qt, et) VALUES(?,?,?)",
                        (task_id, queue_time, exec_time)
                    )
            else:
                if task['r'] < 3:
                    # Exponential backoff retry (1s, 2s, 4s)
                    delay = 1000 * (2 ** task['r'])
                    self.conn.execute(
                        "UPDATE tasks SET s='q', at=?, r=r+1, e=?, unit=NULL WHERE id=?",
                        (now + delay, error, task_id)
                    )
                else:
                    self.conn.execute(
                        "UPDATE tasks SET s='f', et=?, e=?, unit=NULL WHERE id=?",
                        (now, error, task_id)
                    )

    # --- CRUD Operations ---
    def add(self, **kw) -> int:
        """Add a new task to the queue."""
        with self.lock:
            cols = ",".join(kw.keys())
            qs = ",".join("?" for _ in kw)
            cursor = self.conn.execute(f"INSERT INTO tasks({cols}) VALUES({qs})", tuple(kw.values()))
            return cursor.lastrowid

    def get_by_name(self, name: str) -> Optional[sqlite3.Row]:
        with self.lock:
            return self.conn.execute("SELECT * FROM tasks WHERE name=?", (name,)).fetchone()

    def list(self) -> list:
        with self.lock:
            return self.conn.execute("SELECT * FROM tasks ORDER BY ct DESC").fetchall()

    def update_unit(self, task_id: int, unit_name: str, status: str):
        with self.lock:
            self.conn.execute("UPDATE tasks SET unit=?, s=? WHERE id=?", (unit_name, status, task_id))

    def stats(self) -> Dict[str, Any]:
        """Return comprehensive system statistics."""
        with self.lock:
            counts = {r['s']: r['c'] for r in self.conn.execute("SELECT s, COUNT(*) c FROM tasks GROUP BY s")}
            perf = self.conn.execute("SELECT AVG(qt) avg_qt, AVG(et) avg_et, COUNT(*) count FROM metrics").fetchone()
            return {
                'tasks': counts,
                'perf': dict(perf) if perf and perf['avg_qt'] is not None else {}
            }

    def cleanup(self, days: int = 7) -> int:
        """Clean up old completed/failed tasks."""
        cutoff = now_ms() - (days * 86400000)
        with self.lock:
            deleted = self.conn.execute("DELETE FROM tasks WHERE s IN ('d','f') AND et < ?", (cutoff,)).rowcount
            # Vacuum if significantly fragmented (Firefox pattern)
            page_count = self.conn.execute("PRAGMA page_count").fetchone()[0]
            freelist = self.conn.execute("PRAGMA freelist_count").fetchone()[0]
            if freelist > page_count * 0.3:
                self.conn.execute("VACUUM")
            return deleted

# --- Systemd Execution Engine ---
class SystemdExecutor:
    """Handles execution of tasks via systemd-run for resource isolation and management."""
    def __init__(self, store: Store):
        self.store = store

    def launch(self, task: Dict[str, Any]) -> bool:
        """Launch a task using systemd-run with resource controls."""
        unit = unit_name(f"{task['name']}-{task['id']}")
        props = [
            "--property=StandardOutput=journal",
            "--property=StandardError=journal",
            "--property=KillMode=control-group",
        ]

        # Apply resource controls (Integration from Program 2)
        if task.get('rtprio'):
            props.extend([
                "--property=CPUSchedulingPolicy=rr",
                f"--property=CPUSchedulingPriority={task['rtprio']}"
            ])
        if task.get('nice') is not None:
            props.append(f"--property=Nice={int(task['nice'])}")
        if task.get('slice'):
            props.append(f"--slice={task['slice']}")
        if task.get('cpu_weight'):
            props.append(f"--property=CPUWeight={int(task['cpu_weight'])}")
        if task.get('mem_max_mb'):
            props.append(f"--property=MemoryMax={int(task['mem_max_mb'])}M")
        if task.get('cwd'):
            props.append(f"--property=WorkingDirectory={task['cwd']}")

        # Add environment variables
        env = []
        if task.get('env'):
            for k, v in task['env'].items():
                env.extend(["--setenv", f"{k}={v}"])

        # Handle scheduling
        schedule_args = []
        if task.get('schedule'):
            schedule_args.extend(["--on-calendar", task['schedule']])

        # Build and execute the systemd-run command
        cmd_to_run = [task['cmd']] + (task.get('args') or [])
        run_cmd = [*SYSDRUN, "--unit", unit, *props, *env, *schedule_args, "--", *cmd_to_run]

        try:
            cp = subprocess.run(run_cmd, text=True, capture_output=True, timeout=10)
            if cp.returncode == 0:
                status = "sched" if task.get('schedule') else "start"
                self.store.update_unit(task['id'], unit, status)
                return True
            else:
                error_msg = f"Launch failed: {cp.stderr.strip()[:500]}"
                self.store.finalize(task['id'], False, error=error_msg)
                return False
        except subprocess.TimeoutExpired:
            self.store.finalize(task['id'], False, error="Systemd launch timeout")
            return False
        except Exception as e:
            self.store.finalize(task['id'], False, error=f"Systemd launch error: {str(e)}")
            return False

    def reconcile(self) -> int:
        """Reconcile running systemd units with database state."""
        with self.store.lock:
            rows = self.store.conn.execute(
                "SELECT id, unit FROM tasks WHERE s IN ('r', 'start', 'sched') AND unit IS NOT NULL"
            ).fetchall()

        if not rows:
            return 0

        # Query systemd for all relevant units in a single call
        unit_names = [row['unit'] for row in rows]
        cmd = [*SYSTEMCTL, "show", *unit_names, "--property=Id,ActiveState,Result"]
        try:
            cp = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
            if cp.returncode != 0:
                print(f"Warning: Reconciliation failed: {cp.stderr}", file=sys.stderr)
                return 0

            reconciled_count = 0
            # Parse output (blocks separated by empty lines)
            for block in cp.stdout.strip().split('\n\n'):
                if not block:
                    continue
                props = {}
                for line in block.splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        props[key] = value

                unit_id = props.get("Id")
                task_row = next((r for r in rows if r['unit'] == unit_id), None)
                if not task_row:
                    continue

                # Check if the unit has finished
                if props.get("ActiveState") in ("inactive", "failed"):
                    success = (props.get("Result") == "success")
                    error = None if success else f"Systemd Result={props.get('Result')}"
                    self.store.finalize(task_row['id'], success, error)
                    reconciled_count += 1

            return reconciled_count

        except Exception as e:
            print(f"Error during reconciliation: {e}", file=sys.stderr)
            return 0

# --- Worker Process ---
class Worker:
    """Background worker that pulls tasks from the queue and executes them."""
    def __init__(self, store: Store, executor: SystemdExecutor):
        self.store = store
        self.executor = executor
        self.running = True
        self.worker_id = f"w{os.getpid()}"
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, signum, frame):
        print(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def run(self):
        """Main worker loop."""
        print(f"Worker {self.worker_id} started.")
        reconcile_timer = time.time()

        while self.running:
            # Periodic systemd unit reconciliation
            if time.time() - reconcile_timer > 5:
                try:
                    count = self.executor.reconcile()
                    if count > 0:
                        print(f"Reconciled {count} tasks.")
                except Exception as e:
                    print(f"Error in reconciliation: {e}", file=sys.stderr)
                reconcile_timer = time.time()

            # Pull and execute a task
            task = self.store.pop(self.worker_id)
            if task:
                print(f"Launching task {task['id']}: {task['name']}")
                success = self.executor.launch(task)
                if not success:
                    # If systemd launch failed, mark it as a failure immediately
                    self.store.finalize(task['id'], False, error="Failed to launch via systemd")
            else:
                time.sleep(0.1)  # Sleep briefly if no tasks are available

        print("Worker shutdown complete.")

# --- Command Line Interface ---
def main():
    parser = argparse.ArgumentParser(description="Production Job Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add Task
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("name", help="Unique task name")
    add_parser.add_argument("cmd", help="Command to execute")
    add_parser.add_argument("args", nargs="*", help="Command arguments")
    add_parser.add_argument("-p", "--priority", type=int, default=0, help="Task priority (higher = sooner)")
    add_parser.add_argument("--delay", type=int, default=0, help="Delay execution by N seconds")
    add_parser.add_argument("--deps", help="Comma-separated list of dependency task IDs")
    # Resource controls
    add_parser.add_argument("--nice", type=int, help="Nice value for CPU scheduling")
    add_parser.add_argument("--rtprio", type=int, help="Real-time priority (1-99)")
    add_parser.add_argument("--cpu-weight", type=int, help="CPU weight (1-10000)")
    add_parser.add_argument("--mem-max-mb", type=int, help="Memory limit in MB")
    add_parser.add_argument("--schedule", help="Systemd calendar format (e.g., 'daily', '*-*-* 12:00:00')")
    add_parser.add_argument("--env", action="append", help="Environment variables (KEY=VALUE)")
    add_parser.add_argument("--cwd", help="Working directory")

    # Run Worker
    run_parser = subparsers.add_parser("worker", help="Start the task worker/executor")

    # Management Commands
    subparsers.add_parser("stats", help="Show queue statistics")
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old tasks")
    cleanup_parser.add_argument("--days", type=int, default=7, help="Days to keep completed tasks")

    args = parser.parse_args()
    store = Store()

    if args.command == "add":
        try:
            deps = [int(d) for d in args.deps.split(',')] if args.deps else None
        except ValueError:
            sys.exit("Error: Dependencies must be comma-separated integers.")

        config = {}
        if args.nice is not None: config['nice'] = args.nice
        if args.rtprio is not None: config['rtprio'] = args.rtprio
        if args.cpu_weight: config['cpu_weight'] = args.cpu_weight
        if args.mem_max_mb: config['mem_max_mb'] = args.mem_max_mb

        env_dict = {}
        if args.env:
            for e in args.env:
                if "=" in e:
                    k, v = e.split("=", 1)
                    env_dict[k] = v

        at = now_ms() + (args.delay * 1000)
        task_id = store.add(
            name=args.name,
            cmd=args.cmd,
            args=json.dumps(args.args),
            env=json.dumps(env_dict) if env_dict else None,
            cwd=args.cwd,
            p=args.priority,
            at=at,
            dep=json.dumps(deps) if deps else None,
            schedule=args.schedule,
            **config
        )
        print(f"Added Task ID: {task_id}")

    elif args.command == "worker":
        if not shutil.which("systemd-run"):
            sys.exit("Error: 'systemd-run' not found. This orchestrator requires systemd.")
        executor = SystemdExecutor(store)
        worker = Worker(store, executor)
        worker.run()

    elif args.command == "stats":
        print(json.dumps(store.stats(), indent=2))

    elif args.command == "cleanup":
        deleted = store.cleanup(args.days)
        print(f"Cleaned up {deleted} old tasks")

if __name__ == "__main__":
    import shutil
    main()