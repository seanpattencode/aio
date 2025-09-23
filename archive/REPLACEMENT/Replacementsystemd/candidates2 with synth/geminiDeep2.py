#!/usr/bin/env python3
import sqlite3
import subprocess
import logging
import textwrap
import json
from pathlib import Path
import os

# Configuration
DB_PATH = Path.home() / ".aios_workflows.db"
# Use systemd user services for management without root privileges
SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user/"
os.makedirs(SYSTEMD_USER_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO)
UNIT_PREFIX = "aios-"

# AIOS Workflow States
STATE_APPROVED = "approved"

def init_db():
    """Initializes the SQLite database schema with AIOS states and configuration."""
    conn = sqlite3.connect(DB_PATH)
    # Use Write-Ahead Logging (WAL) mode for better concurrency and performance
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workloads (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            command TEXT NOT NULL,
            schedule TEXT,           -- systemd OnCalendar format (e.g., 'daily')
            -- Status: proposed (for review), approved (active), rejected, disabled
            status TEXT DEFAULT 'proposed',
            config TEXT              -- JSON for advanced settings (RT, resources)
        )
    """)
    conn.commit()
    conn.close()

def run_systemctl(args):
    """Executes systemctl --user commands robustly."""
    cmd = ["systemctl", "--user"] + args
    try:
        # Execute command, capturing output silently. check=True raises on failure.
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        # Suppress common "unit not found" or "not loaded" errors during stop/disable, log others
        if "not found" not in e.stderr and "not loaded" not in e.stderr:
            logging.warning(f"systemctl command failed: {' '.join(cmd)}. STDERR: {e.stderr.strip()}")
    except FileNotFoundError:
        logging.error("systemctl command not found. Ensure systemd is installed and running.")

def generate_units(wf, config):
    """Generates systemd service and timer content."""
    # Service Unit: Handles execution and process management
    # KillMode=control-group ensures systemd reaps all child processes (no zombies)
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
    
    # Apply Real-Time scheduling and Resource constraints from config
    # Real-time scheduling (e.g., {"rt_prio": 50, "rt_policy": "rr"})
    if config.get("rt_prio"):
        policy = config.get("rt_policy", "rr")
        service_content += f"CPUSchedulingPolicy={policy}\nCPUSchedulingPriority={config['rt_prio']}\n"
        service_content += "CPUSchedulingResetOnFork=yes\n" # Safety measure

    if config.get("mem_max_mb"):
        service_content += f"MemoryMax={config['mem_max_mb']}M\n"

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
    """The core reconciliation loop: syncs DB state (desired) with systemd (actual)."""
    logging.info("Starting AIOS workload synchronization...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # We only manage workloads that are 'approved' or 'disabled' in systemd
    managed_workflows = {w['name']: w for w in conn.execute("SELECT * FROM workloads WHERE status IN (?, 'disabled')", (STATE_APPROVED,)).fetchall()}
    conn.close()

    # 1. Identify existing AIOS units on the filesystem
    existing_units = set()
    for filename in os.listdir(SYSTEMD_USER_DIR):
        if filename.startswith(UNIT_PREFIX) and (filename.endswith((".service", ".timer"))):
            base_name = filename.replace(UNIT_PREFIX, "").replace(".service", "").replace(".timer", "")
            existing_units.add(base_name)

    # 2. Create/Update units from DB
    for name, wf in managed_workflows.items():
        try:
            config = json.loads(wf['config'] or "{}")
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON config for {name}. Skipping unit file generation.")
            continue

        s_content, t_content = generate_units(wf, config)
        (SYSTEMD_USER_DIR / f"{UNIT_PREFIX}{name}.service").write_text(s_content)
        
        timer_path = SYSTEMD_USER_DIR / f"{UNIT_PREFIX}{name}.timer"
        if t_content:
            timer_path.write_text(t_content)
        elif timer_path.exists():
            # Schedule was removed; stop and delete the timer file
            run_systemctl(["stop", f"{UNIT_PREFIX}{name}.timer"])
            timer_path.unlink()

    # 3. Remove orphaned units (Deleted, rejected, or returned to proposed)
    for name in existing_units - managed_workflows.keys():
        logging.info(f"Removing orphaned/unmanaged workload: {name}")
        run_systemctl(["stop", f"{UNIT_PREFIX}{name}.timer"])
        run_systemctl(["stop", f"{UNIT_PREFIX}{name}.service"])
        (SYSTEMD_USER_DIR / f"{UNIT_PREFIX}{name}.timer").unlink(missing_ok=True)
        (SYSTEMD_USER_DIR / f"{UNIT_PREFIX}{name}.service").unlink(missing_ok=True)

    # 4. Reload systemd configuration to apply file changes
    run_systemctl(["daemon-reload"])

    # 5. Apply desired running state (Start/Stop/Enable/Disable)
    for name, wf in managed_workflows.items():
        # If scheduled, manage the timer; otherwise, manage the service directly.
        target = f"{UNIT_PREFIX}{name}.timer" if wf['schedule'] else f"{UNIT_PREFIX}{name}.service"
        
        if wf['status'] == STATE_APPROVED:
            run_systemctl(["enable", "--now", target])
        elif wf['status'] == 'disabled':
            # Stop the unit now (--now) and disable auto-start on boot
            run_systemctl(["disable", "--now", target])

    logging.info("Synchronization complete.")

if __name__ == '__main__':
    init_db()
    # Run the synchronization whenever the database might have changed.
    sync_workloads()