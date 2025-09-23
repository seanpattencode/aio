#!/usr/bin/env python3
"""
AIOS Orchestrator: Synthesized Production Model
- Uses a single SQLite DB for task state management.
- Delegates all execution and process reaping to transient systemd user units.
- Combines minimalism with production-grade patterns.
"""
import sqlite3
import subprocess
import json
import time
import sys
import shlex
from pathlib import Path

# --- Configuration ---
DB_PATH = Path(__file__).parent / "aios.db"
UNIT_PREFIX = "aios-task-"

class AiosDB:
    """Manages workflow state in a single SQLite database."""
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                cmd TEXT NOT NULL,
                status TEXT DEFAULT 'proposed', -- proposed, approved, running, completed, failed
                rt_prio INTEGER DEFAULT 0, -- 0 for non-real-time, 1-99 for real-time
                schedule TEXT -- systemd OnCalendar string
            );
        """)

    def propose(self, name, cmd, schedule=None, rt_prio=0):
        try:
            return self.conn.execute(
                "INSERT INTO workflows(name, cmd, schedule, rt_prio) VALUES(?,?,?,?)",
                (name, cmd, schedule, rt_prio)
            ).lastrowid
        except sqlite3.IntegrityError:
            print(f"Error: Workflow name '{name}' already exists.", file=sys.stderr)
            return None

    def review(self, name, approve=True):
        status = 'approved' if approve else 'rejected'
        cur = self.conn.execute("UPDATE workflows SET status=? WHERE name=? AND status='proposed'", (status, name))
        if status == 'rejected':
            self.conn.execute("DELETE FROM workflows WHERE name=?", (name,))
        return cur.rowcount > 0

    def get_approved_workflow(self):
        # Atomically fetch and mark the next 'approved' task as 'running'
        try:
            cur = self.conn.execute("""
                UPDATE workflows SET status='running' WHERE id = (
                    SELECT id FROM workflows WHERE status='approved' LIMIT 1
                ) RETURNING id, name, cmd, schedule, rt_prio
            """)
            row = cur.fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError: # Fallback for older SQLite
            with self.conn:
                row = self.conn.execute("SELECT * FROM workflows WHERE status='approved' LIMIT 1").fetchone()
                if not row: return None
                self.conn.execute("UPDATE workflows SET status='running' WHERE id=?", (row['id'],))
                return dict(row)

    def finalize(self, name, success):
        status = 'completed' if success else 'failed'
        self.conn.execute("UPDATE workflows SET status=? WHERE name=?", (status, name))

class SystemdManager:
    """Delegates command execution to transient systemd --user units."""
    def _run(self, args, check=False):
        return subprocess.run(args, capture_output=True, text=True, check=check)

    def execute(self, wf):
        """Runs a workflow using systemd-run, returning the generated unit name."""
        unit_name = f"{UNIT_PREFIX}{wf['name']}.service"
        args = ["systemd-run", "--user", "--unit", unit_name, "--collect",
                "--property=KillMode=control-group",
                "--property=StandardOutput=journal",
                "--property=StandardError=journal"]
        if wf['schedule']:
            args.append(f"--on-calendar={wf['schedule']}")
        if wf['rt_prio'] and 1 <= wf['rt_prio'] <= 99:
            args.extend([f"--property=CPUSchedulingPolicy=rr",
                         f"--property=CPUSchedulingPriority={wf['rt_prio']}"])
        args.extend(shlex.split(wf['cmd']))

        proc = self._run(args)
        if proc.returncode != 0:
            print(f"Error launching systemd unit for '{wf['name']}': {proc.stderr}", file=sys.stderr)
            return None
        return unit_name

    def get_status(self, unit_name):
        """Checks the status of a systemd unit. Returns (state, result)."""
        proc = self._run(["systemctl", "--user", "show", unit_name, "--property=ActiveState,Result"])
        props = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines() if "=" in line)
        return props.get("ActiveState"), props.get("Result")

def worker_loop(db, manager):
    """Main daemon loop to process approved workflows."""
    print(f"AIOS Worker started (PID: {os.getpid()}). Polling for approved workflows...")
    running = {} # Maps workflow name to unit name

    def shutdown(signum, frame):
        print("\nShutdown signal received. AIOS worker stopping.")
        nonlocal running
        running = None # Sentinel to break loop
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while running is not None:
        # 1. Launch new approved workflows
        if len(running) < os.cpu_count(): # Simple concurrency limit
            wf = db.get_approved_workflow()
            if wf:
                print(f"Launching workflow '{wf['name']}'...")
                unit_name = manager.execute(wf)
                if unit_name:
                    running[wf['name']] = unit_name
                else:
                    db.finalize(wf['name'], success=False)

        # 2. Check status of running workflows
        for wf_name, unit_name in list(running.items()):
            state, result = manager.get_status(unit_name)
            if state in ('inactive', 'failed', 'deactivating'):
                success = (result == 'success')
                print(f"Workflow '{wf_name}' finished. Success: {success}")
                db.finalize(wf_name, success)
                del running[wf_name]

        time.sleep(2) # Poll interval
    print("Worker loop finished.")

def main():
    """CLI to manage and run the AIOS orchestrator."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <propose|review|worker>", file=sys.stderr)
        sys.exit(1)

    db = AiosDB()
    cmd = sys.argv[1]

    if cmd == 'propose':
        if len(sys.argv) < 4:
            print(f"Usage: {sys.argv[0]} propose <name> <command> [--schedule='...'] [--rt=prio]", file=sys.stderr)
            sys.exit(1)
        name, command = sys.argv[2], sys.argv[3]
        schedule = next((arg.split('=')[1] for arg in sys.argv[4:] if arg.startswith('--schedule')), None)
        rt_prio = int(next((arg.split('=')[1] for arg in sys.argv[4:] if arg.startswith('--rt')), 0))
        if db.propose(name, command, schedule, rt_prio):
            print(f"Workflow '{name}' proposed for review.")

    elif cmd == 'review':
        if len(sys.argv) != 4 or sys.argv[3] not in ['accept', 'reject']:
            print(f"Usage: {sys.argv[0]} review <name> <accept|reject>", file=sys.stderr)
            sys.exit(1)
        name, action = sys.argv[2], sys.argv[3]
        if db.review(name, approve=(action == 'accept')):
            print(f"Workflow '{name}' has been {action}ed.")
        else:
            print(f"Error: Could not find proposed workflow '{name}'.", file=sys.stderr)

    elif cmd == 'worker':
        manager = SystemdManager()
        worker_loop(db, manager)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)

if __name__ == "__main__":
    main()