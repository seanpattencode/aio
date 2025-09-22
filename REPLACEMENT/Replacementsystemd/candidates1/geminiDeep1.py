#!/usr/bin/env python3
import sqlite3
import subprocess
import os
import logging
import textwrap

# Configuration
DB_PATH = os.path.expanduser("~/aios_workflows.db")
# Using systemd user services for management without root
SYSTEMD_USER_DIR = os.path.expanduser("~/.config/systemd/user/")
os.makedirs(SYSTEMD_USER_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO)
UNIT_PREFIX = "aios-"

def init_db():
    """Initializes the SQLite database schema."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workloads (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            command TEXT NOT NULL,
            schedule TEXT,
            realtime_prio INTEGER,
            enabled INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def run_systemctl(args):
    """Executes systemctl --user commands."""
    cmd = ["systemctl", "--user"] + args
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"systemctl failed: {' '.join(cmd)}. Error: {e.stderr.decode().strip()}")

def generate_units(wf):
    """Generates systemd service and timer content."""
    # Service Unit: Handles execution, reaping, and RT scheduling
    service_content = textwrap.dedent(f"""\
    [Unit]
    Description=AIOS Workload: {wf['name']}
    [Service]
    Type=simple
    ExecStart={wf['command']}
    Restart=on-failure
    KillMode=control-group
    Environment="PYTHONUNBUFFERED=1"
    """)
    
    # Real-time scheduling (Note: often requires configuration of user limits)
    if wf['realtime_prio'] and wf['realtime_prio'] > 0:
        service_content += f"CPUSchedulingPolicy=rr\nCPUSchedulingPriority={wf['realtime_prio']}\nCPUSchedulingResetOnFork=yes\n"

    # Timer Unit: Handles complex scheduling
    timer_content = None
    if wf['schedule']:
        timer_content = textwrap.dedent(f"""\
        [Unit]
        Description=AIOS Scheduler for: {wf['name']}
        [Timer]
        OnCalendar={wf['schedule']}
        Persistent=true
        [Install]
        WantedBy=timers.target
        """)
    return service_content, timer_content

def sync_workloads():
    """Synchronizes the database state with systemd units."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    workflows = {w['name']: w for w in conn.execute("SELECT * FROM workloads").fetchall()}
    conn.close()

    # 1. Identify existing AIOS units on the filesystem
    existing_units = set()
    for filename in os.listdir(SYSTEMD_USER_DIR):
        if filename.startswith(UNIT_PREFIX) and (filename.endswith(".service") or filename.endswith(".timer")):
            base_name = filename.replace(UNIT_PREFIX, "").replace(".service", "").replace(".timer", "")
            existing_units.add(base_name)

    # 2. Create/Update units from DB
    for name, wf in workflows.items():
        s_content, t_content = generate_units(wf)
        with open(os.path.join(SYSTEMD_USER_DIR, f"{UNIT_PREFIX}{name}.service"), "w") as f:
            f.write(s_content)
        
        timer_path = os.path.join(SYSTEMD_USER_DIR, f"{UNIT_PREFIX}{name}.timer")
        if t_content:
            with open(timer_path, "w") as f:
                f.write(t_content)
        elif os.path.exists(timer_path):
            # Schedule removed; clean up the timer file
            run_systemctl(["stop", f"{UNIT_PREFIX}{name}.timer"])
            os.remove(timer_path)

    # 3. Remove orphaned units (Deleted from DB)
    for name in existing_units - workflows.keys():
        logging.info(f"Removing orphaned workload: {name}")
        run_systemctl(["stop", f"{UNIT_PREFIX}{name}.timer"])
        run_systemctl(["stop", f"{UNIT_PREFIX}{name}.service"])
        run_systemctl(["disable", f"{UNIT_PREFIX}{name}.timer"])
        run_systemctl(["disable", f"{UNIT_PREFIX}{name}.service"])
        if os.path.exists(os.path.join(SYSTEMD_USER_DIR, f"{UNIT_PREFIX}{name}.timer")):
             os.remove(os.path.join(SYSTEMD_USER_DIR, f"{UNIT_PREFIX}{name}.timer"))
        if os.path.exists(os.path.join(SYSTEMD_USER_DIR, f"{UNIT_PREFIX}{name}.service")):
             os.remove(os.path.join(SYSTEMD_USER_DIR, f"{UNIT_PREFIX}{name}.service"))

    # 4. Reload systemd configuration
    run_systemctl(["daemon-reload"])

    # 5. Apply desired state (Start/Stop/Enable/Disable)
    for name, wf in workflows.items():
        # Determine the primary unit to manage
        target = f"{UNIT_PREFIX}{name}.timer" if wf['schedule'] else f"{UNIT_PREFIX}{name}.service"
        
        if wf['enabled']:
            run_systemctl(["enable", "--now", target])
        else:
            run_systemctl(["disable", "--now", target])

if __name__ == '__main__':
    init_db()
    # This sync function ensures the systemd state matches the database configuration.
    sync_workloads()
    logging.info("AIOS workload synchronization complete.")
    # Note for systemd --user: Ensure 'linger' is enabled for the user if workloads
    # must run without an active login session (e.g., `loginctl enable-linger $USER`).