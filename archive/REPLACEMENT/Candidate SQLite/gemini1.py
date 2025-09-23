#!/usr/bin/env python3
"""
AIOS Orchestrator - Systemd with SQLite Task Queue
Combines a persistent SQLite task queue with the robustness of systemd.
"""
import os
import sys
import time
import subprocess
import json
import sqlite3
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_queue.db"
UNIT_PREFIX = "aios-"
POLL_INTERVAL_SECONDS = 5

# --- SQLite Task Queue Class ---
class SQLiteQueue:
    """Manages the persistent task queue in an SQLite database."""
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                command TEXT NOT NULL,
                desired_state TEXT DEFAULT 'running' CHECK(desired_state IN ('running', 'stopped')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    def add_job(self, name, command):
        """Adds or updates a job in the database, setting its desired state to 'running'."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO jobs (name, command, desired_state) VALUES (?, ?, 'running') "
                "ON CONFLICT(name) DO UPDATE SET command=excluded.command, desired_state='running'",
                (name, command)
            )
        return True

    def set_desired_state(self, name, state):
        """Sets the desired state for a job (e.g., 'stopped')."""
        if state not in ['running', 'stopped']:
            return False
        with self.conn:
            self.conn.execute("UPDATE jobs SET desired_state = ? WHERE name = ?", (state, name))
        return True

    def get_desired_state(self):
        """Gets the desired state of all jobs from the database."""
        cursor = self.conn.execute("SELECT name, command, desired_state FROM jobs")
        return {row['name']: {'command': row['command'], 'state': row['desired_state']} for row in cursor.fetchall()}

    def close(self):
        self.conn.close()

# --- Systemd Orchestrator Class (Your existing code, slightly modified) ---
class SystemdOrchestrator:
    """Minimal systemd wrapper - let systemd handle everything"""
    def _run(self, *args):
        """Run systemctl command, returning the result object."""
        return subprocess.run(["systemctl", "--user"] + list(args),
                            capture_output=True, text=True, check=False)

    def generate_and_load_unit(self, name: str, command: str, restart: str = "always"):
        """Creates the systemd unit file and reloads the daemon."""
        unit_name = f"{UNIT_PREFIX}{name}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_content = f"""[Unit]
Description=AIOS Job: {name}
[Service]
ExecStart=/bin/sh -c '{command}'
Restart={restart}
RestartSec=1
StandardOutput=journal
StandardError=journal
KillMode=control-group
[Install]
WantedBy=default.target
"""
        unit_path.write_text(unit_content)
        self._run("daemon-reload")

    def start_job(self, name: str):
        return self._run("start", f"{UNIT_PREFIX}{name}.service")

    def stop_job(self, name: str):
        return self._run("stop", f"{UNIT_PREFIX}{name}.service")

    def get_actual_state(self) -> dict:
        """Get the actual state of all AIOS jobs from systemd."""
        result = self._run("list-units", f"{UNIT_PREFIX}*.service", "--all", "--no-legend", "--plain")
        actual_state = {}
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split(maxsplit=4)
            unit_name_full = parts[0]
            name = unit_name_full.replace('.service', '').replace(UNIT_PREFIX, '')
            actual_state[name] = {
                'load': parts[1],
                'active': parts[2], # active, inactive, failed
                'sub': parts[3],    # running, dead, exited
                'description': parts[4]
            }
        return actual_state

# --- Main Application & CLI ---
def run_orchestrator(queue, systemd):
    """The main reconciliation loop."""
    print("🚀 AIOS orchestrator running... Press Ctrl+C to exit.")
    while True:
        try:
            # 1. Get Desired State (from DB)
            desired_state = queue.get_desired_state()

            # 2. Get Actual State (from systemd)
            actual_state = systemd.get_actual_state()

            # 3. Reconcile
            all_job_names = set(desired_state.keys()) | set(actual_state.keys())

            for name in all_job_names:
                desired = desired_state.get(name, {}).get('state')
                actual = actual_state.get(name)
                is_active = actual and actual.get('active') == 'active'

                # Case 1: Job should be running, but isn't.
                if desired == 'running' and not is_active:
                    print(f"✅ Reconciling '{name}': State is '{actual.get('active', 'missing')}', desired is 'running'. Starting...")
                    systemd.generate_and_load_unit(name, desired_state[name]['command'])
                    systemd.start_job(name)

                # Case 2: Job should be stopped, but is running.
                elif desired == 'stopped' and is_active:
                    print(f"🛑 Reconciling '{name}': State is 'active', desired is 'stopped'. Stopping...")
                    systemd.stop_job(name)

            time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nShutting down orchestrator.")
            break
        except Exception as e:
            print(f"🚨 An error occurred in the reconciliation loop: {e}")
            time.sleep(POLL_INTERVAL_SECONDS * 2) # Wait a bit longer after an error

def main():
    """Main entry point for CLI and daemon."""
    queue = SQLiteQueue(DB_PATH)
    systemd = SystemdOrchestrator()

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <run|add|stop|status>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "run":
        run_orchestrator(queue, systemd)
    elif cmd == "add":
        if len(sys.argv) != 4:
            print(f"Usage: {sys.argv[0]} add <name> '<command>'")
            sys.exit(1)
        queue.add_job(sys.argv[2], sys.argv[3])
        print(f"Job '{sys.argv[2]}' added to the queue. The running orchestrator will start it.")
    elif cmd == "stop":
        if len(sys.argv) != 3:
            print(f"Usage: {sys.argv[0]} stop <name>")
            sys.exit(1)
        queue.set_desired_state(sys.argv[2], 'stopped')
        print(f"Job '{sys.argv[2]}' marked for stopping. The running orchestrator will stop it.")
    elif cmd == "status":
        print(json.dumps(systemd.get_actual_state(), indent=2))
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()