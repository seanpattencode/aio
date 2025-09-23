#!/usr/bin/env python3
"""
Integrated Job Orchestrator: High-Performance Queue + Asynchronous Systemd Execution
"""
import sqlite3, subprocess, json, time, sys, os, signal, threading, argparse, shutil
from typing import Optional, Dict, Any, List
from pathlib import Path

# --- Configuration ---
DB_PATH = Path.home() / ".orchestrator.db"
MAX_RETRIES = 3
UNIT_PREFIX = "orch-"

# Optimized SQLite pragmas
PRAGMAS = [
    "PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000", "PRAGMA temp_store=MEMORY"
]

# Systemd configuration - Use user scope if not root
USE_USER = (os.geteuid() != 0)
SYSTEMD_ARGS = ["--user"] if USE_USER else []
# systemd-run without --collect returns immediately (Asynchronous)
SYSDRUN = ["systemd-run", *SYSTEMD_ARGS, "--quiet"]
SYSTEMCTL = ["systemctl", *SYSTEMD_ARGS]

# --- Task Queue Logic ---

class TaskQueue:
    """Thread-safe, high-performance queue with dependencies and resource management."""

    def __init__(self, db_path=DB_PATH):
        # Persistent connection, isolation_level=None for speed, manual locking
        self.conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            for pragma in PRAGMAS:
                self.conn.execute(pragma)

            # Unified Schema. S (Status): Q=queued R=running D=done F=failed
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    cmd TEXT NOT NULL,
                    P INTEGER DEFAULT 0,    -- Priority
                    S TEXT DEFAULT 'Q',     -- Status
                    AT INTEGER DEFAULT 0,   -- Scheduled At (ms)
                    R INTEGER DEFAULT 0,    -- Retries
                    DEP TEXT,               -- JSON dependencies
                    CONF TEXT,              -- JSON resource config {nice, cpu, mem}
                    UNIT TEXT,              -- Systemd Unit Name
                    ERR TEXT,               -- Error snippet
                    CT INTEGER DEFAULT (CAST(strftime('%s', 'now') AS INTEGER) * 1000), -- Created
                    ST INTEGER, ET INTEGER  -- Start/End time
                );
                -- Optimized index for fetching tasks
                CREATE INDEX IF NOT EXISTS idx_fetch ON tasks(S, P DESC, AT, id)
                WHERE S = 'Q';

                -- Metrics table
                CREATE TABLE IF NOT EXISTS metrics (
                    task_id INTEGER PRIMARY KEY, qt_s REAL, et_s REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
            """)

    def add(self, cmd: str, priority: int = 0, delay_s: int = 0, deps: Optional[list] = None, config: Optional[dict] = None) -> int:
        """Add a task to the queue."""
        at = int(time.time() * 1000) + (delay_s * 1000)
        dep_json = json.dumps(deps) if deps else None
        conf_json = json.dumps(config) if config else None

        with self.lock:
            return self.conn.execute(
                "INSERT INTO tasks(cmd, P, AT, DEP, CONF) VALUES(?,?,?,?,?)",
                (cmd, priority, at, dep_json, conf_json)
            ).lastrowid

    def pop(self) -> Optional[Dict[str, Any]]:
        """Atomically claim the next eligible task, respecting dependencies."""
        now = int(time.time() * 1000)

        # Query finds the highest priority, oldest scheduled task where dependencies are 'D'one.
        query = """
            SELECT id FROM tasks t
            WHERE S='Q' AND AT<=:now
            AND (DEP IS NULL OR NOT EXISTS (
                SELECT 1 FROM json_each(t.DEP) AS d
                JOIN tasks AS dt ON dt.id = d.value
                WHERE dt.S != 'D'
            ))
            ORDER BY P DESC, AT, id
            LIMIT 1
        """

        with self.lock:
            # 1. Find the task ID
            row = self.conn.execute(query, {'now': now}).fetchone()
            if not row:
                return None

            # 2. Atomically claim it using UPDATE...RETURNING (prevents race conditions)
            try:
                result = self.conn.execute("""
                    UPDATE tasks SET S='R', ST=:now
                    WHERE id=:id AND S='Q'
                    RETURNING id, cmd, CONF
                """, {'now': now, 'id': row['id']}).fetchone()

                if result:
                    task = dict(result)
                    task['CONF'] = json.loads(task['CONF']) if task['CONF'] else {}
                    return task
            except sqlite3.OperationalError:
                 # Handle older SQLite versions if necessary (omitted for brevity)
                 pass
            return None

    def update_running(self, task_id: int, unit_name: str):
        """Associate the systemd unit with the task."""
        with self.lock:
            self.conn.execute("UPDATE tasks SET UNIT=? WHERE id=?", (unit_name, task_id))

    def finalize(self, task_id: int, success: bool, error: str = None):
        """Mark task as complete (D/F) or schedule retry (Q), and record metrics."""
        now = int(time.time() * 1000)

        with self.lock:
            task = self.conn.execute("SELECT R, CT, ST FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task: return

            if success:
                self.conn.execute("UPDATE tasks SET S='D', ET=?, UNIT=NULL WHERE id=?", (now, task_id))
                self._record_metrics(task_id, task, now)
            elif task['R'] < MAX_RETRIES:
                # Exponential backoff (1s, 2s, 4s...)
                delay = 1000 * (2 ** task['R'])
                self.conn.execute(
                    "UPDATE tasks SET S='Q', AT=?, R=R+1, ERR=?, UNIT=NULL WHERE id=?",
                    (now + delay, error, task_id)
                )
            else:
                self.conn.execute(
                    "UPDATE tasks SET S='F', ET=?, ERR=?, UNIT=NULL WHERE id=?",
                    (now, error, task_id)
                )
                self._record_metrics(task_id, task, now)

    def _record_metrics(self, task_id, task, now):
        if task['ST'] and task['CT']:
            qt = (task['ST'] - task['CT']) / 1000.0
            et = (now - task['ST']) / 1000.0
            self.conn.execute(
                "INSERT OR REPLACE INTO metrics(task_id, qt_s, et_s) VALUES(?,?,?)",
                (task_id, qt, et)
            )

    def get_running_units(self) -> Dict[str, int]:
        """Get map of unit names to task IDs for running tasks."""
        with self.lock:
            rows = self.conn.execute("SELECT id, UNIT FROM tasks WHERE S='R' AND UNIT IS NOT NULL").fetchall()
            return {row['UNIT']: row['id'] for row in rows}

    def stats(self) -> Dict[str, Any]:
        with self.lock:
            counts = {r['S']: r['C'] for r in self.conn.execute("SELECT S, COUNT(*) C FROM tasks GROUP BY S")}
            perf = self.conn.execute("SELECT AVG(qt_s) avg_qt, AVG(et_s) avg_et, COUNT(*) count FROM metrics").fetchone()
            return {'tasks': counts, 'perf_s': dict(perf) if perf and perf['avg_qt'] is not None else {}}

# --- Executor Logic ---

class AsyncExecutor:
    """Pulls tasks and executes them asynchronously using systemd-run."""

    def __init__(self, queue: TaskQueue):
        self.queue = queue
        self.running = True

    def launch_task(self, task: Dict[str, Any]):
        """Launch a single task using systemd-run with resource controls."""
        task_id = task['id']
        config = task['CONF']
        # Unique unit name ensures clean runs, especially for retries
        unit_name = f"{UNIT_PREFIX}{task_id}-{int(time.time())}.service"

        props = ["--property=KillMode=control-group"]
        
        # Apply resource controls (Integration from Program 2)
        if config.get('nice') is not None:
            props.append(f"--property=Nice={int(config['nice'])}")
        if config.get('cpu_weight'):
             props.append(f"--property=CPUWeight={int(config['cpu_weight'])}")
        if config.get('mem_max_mb'):
             props.append(f"--property=MemoryMax={int(config['mem_max_mb'])}M")

        # Wrap command in 'sh -c' for shell interpretation
        cmd_to_run = ["sh", "-c", task['cmd']]
        run_cmd = [*SYSDRUN, "--unit", unit_name, *props, "--", *cmd_to_run]

        # Launch the command (returns immediately)
        cp = subprocess.run(run_cmd, text=True, capture_output=True)

        if cp.returncode == 0:
            # Successfully launched, update DB so reconciler can track it
            self.queue.update_running(task_id, unit_name)
        else:
            # Failed to launch (e.g., systemd issue)
            error_msg = f"Launch failed: {cp.stderr.strip()[:500]}"
            self.queue.finalize(task_id, False, error=error_msg)

    def reconcile(self):
        """Check the status of running systemd units and update the database."""
        unit_map = self.queue.get_running_units()
        if not unit_map:
            return 0

        # Efficiently query systemd for multiple units at once
        cmd = [*SYSTEMCTL, "show", *unit_map.keys(), "--property=Id,ActiveState,Result"]
        cp = subprocess.run(cmd, text=True, capture_output=True)

        if cp.returncode != 0:
            print(f"Warning: Reconciliation failed: {cp.stderr}", file=sys.stderr)
            return 0

        # Parse the output (blocks separated by empty lines)
        reconciled_count = 0
        for block in cp.stdout.strip().split('\n\n'):
            props = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
            unit_id = props.get("Id")
            task_id = unit_map.get(unit_id)

            if not task_id: continue

            # Check if the unit has finished
            if props.get("ActiveState") in ("inactive", "failed"):
                success = (props.get("Result") == "success")
                error = None if success else f"Systemd Result={props.get('Result')}"
                self.queue.finalize(task_id, success, error)
                reconciled_count += 1
        return reconciled_count

    def run_loop(self, poll_interval=0.5):
        """Main processing loop."""
        print(f"Executor started. Systemd scope: {'User' if USE_USER else 'System'}")
        self._setup_signals()
        reconcile_timer = time.time()

        while self.running:
            # 1. Periodic Reconciliation (e.g., every 5 seconds)
            if time.time() - reconcile_timer > 5:
                try:
                    count = self.reconcile()
                    if count > 0: print(f"Reconciled {count} tasks.")
                except Exception as e:
                    print(f"Error during reconciliation: {e}", file=sys.stderr)
                reconcile_timer = time.time()

            # 2. Launch new tasks
            try:
                task = self.queue.pop()
                if task:
                    self.launch_task(task)
                else:
                    time.sleep(poll_interval)
            except Exception as e:
                print(f"Error in executor loop: {e}", file=sys.stderr)
                time.sleep(5) # Back off if DB is failing

        print("Executor shutting down.")

    def _setup_signals(self):
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, *_):
        self.running = False

# --- CLI and Main ---

def main():
    parser = argparse.ArgumentParser(description="Integrated Job Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add Task
    add_p = subparsers.add_parser("add", help="Add a new task")
    add_p.add_argument("cmd", help="The command to execute (shell string)")
    add_p.add_argument("-p", "--priority", type=int, default=0)
    add_p.add_argument("--delay", type=int, default=0, help="Delay in seconds")
    add_p.add_argument("--deps", help="Comma-separated list of dependency task IDs")
    # Resource controls
    add_p.add_argument("--nice", type=int)
    add_p.add_argument("--cpu-weight", type=int)
    add_p.add_argument("--mem-max-mb", type=int)

    # Run Executor
    run_p = subparsers.add_parser("run", help="Start the task executor/worker")
    run_p.add_argument("--poll", type=float, default=0.5)

    subparsers.add_parser("stats", help="Show queue statistics")

    # Display help if no command is provided
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
        
    args = parser.parse_args()
    q = TaskQueue()

    if args.command == "add":
        try:
            deps = [int(d) for d in args.deps.split(',')] if args.deps else None
        except ValueError:
            sys.exit("Error: Dependencies must be comma-separated integers.")
        
        config = {}
        if args.nice is not None: config['nice'] = args.nice
        if args.cpu_weight: config['cpu_weight'] = args.cpu_weight
        if args.mem_max_mb: config['mem_max_mb'] = args.mem_max_mb

        task_id = q.add(args.cmd, args.priority, args.delay, deps, config)
        print(f"Added Task ID: {task_id}")

    elif args.command == "run":
        if not shutil.which("systemd-run"):
            sys.exit("Error: systemd-run not found. This orchestrator requires systemd.")
        executor = AsyncExecutor(q)
        executor.run_loop(args.poll)

    elif args.command == "stats":
        print(json.dumps(q.stats(), indent=2))

if __name__ == "__main__":
    main()