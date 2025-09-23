#!/usr/bin/env python3
import os
import sys
import sqlite3
import subprocess
import signal
from pathlib import Path

DB_PATH = Path("/var/lib/aios/workflows.db")
SYSTEMD_DIR = Path("/etc/systemd/system/")

class AIOSManager:
    def __init__(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)
        self.init_db()

    def init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                script_path TEXT,
                schedule TEXT,
                enabled BOOLEAN DEFAULT 1,
                accepted BOOLEAN DEFAULT 0
            )
        """)
        self.db.commit()

    def register_workflow(self, name, script, schedule="*-*-* *:*:00"):
        if not Path(script).exists():
            raise FileNotFoundError(f"Script {script} not found")
        self.db.execute(
            "INSERT OR REPLACE INTO workflows (name, script_path, schedule, accepted) VALUES (?, ?, ?, 1)",
            (name, script, schedule)
        )
        self.db.commit()
        self.write_systemd_unit(name, script, schedule)

    def write_systemd_unit(self, name, script, schedule):
        unit_name = f"aios-{name}.service"
        timer_name = f"aios-{name}.timer"
        service_content = f"""[Unit]
Description=AIOS Workflow - {name}
After=network.target

[Service]
Type=exec
ExecStart={sys.executable} {script}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
KillMode=process

[Install]
WantedBy=multi-user.target
"""
        timer_content = f"""[Unit]
Description=AIOS Timer for {name}

[Timer]
OnCalendar={schedule}
Persistent=true

[Install]
WantedBy=timers.target
"""
        (SYSTEMD_DIR / unit_name).write_text(service_content)
        (SYSTEMD_DIR / timer_name).write_text(timer_content)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", timer_name], check=True)
        subprocess.run(["systemctl", "start", timer_name], check=True)

    def list_workflows(self):
        return self.db.execute("SELECT name, script_path, schedule, enabled FROM workflows WHERE accepted = 1").fetchall()

    def approve_workflow(self, name):
        self.db.execute("UPDATE workflows SET accepted = 1 WHERE name = ?", (name,))
        self.db.commit()

    def reject_workflow(self, name):
        self.db.execute("UPDATE workflows SET accepted = 0 WHERE name = ?", (name,))
        self.db.commit()
        self.disable_workflow(name)

    def disable_workflow(self, name):
        timer_name = f"aios-{name}.timer"
        service_name = f"aios-{name}.service"
        subprocess.run(["systemctl", "stop", timer_name], stderr=subprocess.DEVNULL)
        subprocess.run(["systemctl", "disable", timer_name], stderr=subprocess.DEVNULL)
        (SYSTEMD_DIR / timer_name).unlink(missing_ok=True)
        (SYSTEMD_DIR / service_name).unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], check=True)

if __name__ == "__main__":
    mgr = AIOSManager()
    print("AIOS Systemd Workflow Manager (v0.1)")
    print("Workflows:", mgr.list_workflows())