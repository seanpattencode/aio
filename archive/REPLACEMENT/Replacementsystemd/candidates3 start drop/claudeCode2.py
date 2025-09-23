#!/usr/bin/env python3
"""
claudeCode2: Enhanced Features with SQLite State (<150 lines)
Combines: chatgpt1 + kimi1 + systemdOrchestrator patterns
Best for: Stateful workflows, scheduling, persistence
"""
import sqlite3
import subprocess
import json
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List

DB_PATH = Path.home() / ".aios_state.db"
USER_DIR = Path.home() / ".config/systemd/user"
UNIT_PREFIX = "aios-"

class EnhancedOrchestrator:
    """Systemd orchestrator with SQLite state management"""

    def __init__(self):
        USER_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                name TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                type TEXT DEFAULT 'service',
                schedule TEXT,
                realtime INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'inactive',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.commit()

    def _systemctl(self, *args) -> subprocess.CompletedProcess:
        """Execute systemctl --user command"""
        return subprocess.run(["systemctl", "--user"] + list(args),
                            capture_output=True, text=True)

    def create_service(self, name: str, command: str,
                      realtime: bool = False, priority: int = 0) -> bool:
        """Create persistent systemd service"""
        unit_file = USER_DIR / f"{UNIT_PREFIX}{name}.service"

        # Generate service content
        content = f"""[Unit]
Description=AIOS Workflow: {name}
After=network.target

[Service]
Type=simple
ExecStart=/bin/sh -c '{command}'
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
"""
        if realtime:
            content += f"""CPUSchedulingPolicy=rr
CPUSchedulingPriority={min(99, max(1, priority))}
"""

        content += "\n[Install]\nWantedBy=default.target\n"

        # Write unit file
        unit_file.write_text(content)

        # Store in database
        self.db.execute("""
            INSERT OR REPLACE INTO workflows
            (name, command, type, realtime, priority)
            VALUES (?, ?, 'service', ?, ?)
        """, (name, command, int(realtime), priority))
        self.db.commit()

        # Reload and enable
        self._systemctl("daemon-reload")
        result = self._systemctl("enable", "--now", f"{UNIT_PREFIX}{name}.service")

        if result.returncode == 0:
            self.db.execute("UPDATE workflows SET status='active' WHERE name=?", (name,))
            self.db.commit()
            return True
        return False

    def create_timer(self, name: str, command: str, schedule: str) -> bool:
        """Create scheduled task with systemd timer"""
        # First create the service
        self.create_service(name, command)

        # Create timer
        timer_file = USER_DIR / f"{UNIT_PREFIX}{name}.timer"
        timer_content = f"""[Unit]
Description=Timer for AIOS Workflow: {name}

[Timer]
OnCalendar={schedule}
Persistent=true

[Install]
WantedBy=timers.target
"""
        timer_file.write_text(timer_content)

        # Update database
        self.db.execute("""
            UPDATE workflows SET type='timer', schedule=? WHERE name=?
        """, (schedule, name))
        self.db.commit()

        # Enable timer
        self._systemctl("daemon-reload")
        result = self._systemctl("enable", "--now", f"{UNIT_PREFIX}{name}.timer")
        return result.returncode == 0

    def run_transient(self, name: str, command: str, delay_sec: int = 0) -> bool:
        """Run transient unit (no files created)"""
        unit = f"{UNIT_PREFIX}transient-{name}"
        args = ["systemd-run", "--user", "--unit", unit, "--collect"]

        if delay_sec > 0:
            args.append(f"--on-active={delay_sec}")

        args.extend(["--", "sh", "-c", command])

        result = subprocess.run(args, capture_output=True)
        return result.returncode == 0

    def list_workflows(self) -> List[Dict]:
        """List all workflows with current status"""
        cursor = self.db.execute("""
            SELECT name, command, type, schedule, status FROM workflows
            ORDER BY created_at DESC
        """)

        workflows = []
        for row in cursor:
            name = row[0]
            # Get live status
            unit = f"{UNIT_PREFIX}{name}.{'timer' if row[2] == 'timer' else 'service'}"
            result = self._systemctl("is-active", unit)
            live_status = result.stdout.strip()

            workflows.append({
                'name': name,
                'command': row[1],
                'type': row[2],
                'schedule': row[3],
                'status': live_status
            })
        return workflows

    def remove(self, name: str) -> bool:
        """Remove workflow completely"""
        # Stop and disable units
        for suffix in ['.service', '.timer']:
            unit = f"{UNIT_PREFIX}{name}{suffix}"
            self._systemctl("stop", unit)
            self._systemctl("disable", unit)
            unit_file = USER_DIR / unit
            unit_file.unlink(missing_ok=True)

        # Remove from database
        self.db.execute("DELETE FROM workflows WHERE name=?", (name,))
        self.db.commit()

        self._systemctl("daemon-reload")
        return True

def main():
    """CLI interface"""
    if len(sys.argv) < 2:
        print("Usage: claudeCode2.py <service|timer|transient|list|remove> [args...]")
        sys.exit(1)

    orch = EnhancedOrchestrator()
    cmd = sys.argv[1]

    if cmd == "service" and len(sys.argv) >= 4:
        if orch.create_service(sys.argv[2], sys.argv[3]):
            print(f"Service created: {sys.argv[2]}")

    elif cmd == "timer" and len(sys.argv) >= 5:
        if orch.create_timer(sys.argv[2], sys.argv[3], sys.argv[4]):
            print(f"Timer created: {sys.argv[2]}")

    elif cmd == "transient" and len(sys.argv) >= 4:
        if orch.run_transient(sys.argv[2], sys.argv[3]):
            print(f"Transient unit started: {sys.argv[2]}")

    elif cmd == "list":
        for wf in orch.list_workflows():
            print(json.dumps(wf))

    elif cmd == "remove" and len(sys.argv) >= 3:
        if orch.remove(sys.argv[2]):
            print(f"Removed: {sys.argv[2]}")

if __name__ == "__main__":
    main()