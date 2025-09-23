#!/usr/bin/env python3
"""
AIOS Workflow Manager - Synthesized from best practices
- Uses file-based units for persistence
- pystemd for direct control (pip install pystemd)
- sdnotify and journal for integration
- SQLite for state with approval flow
- Real-time scheduling, timers for complex schedules
- Graceful shutdown, no manual reaping (systemd handles)
"""
import sqlite3
import os
import sys
import time
import signal
import logging
from pathlib import Path
try:
    from pystemd.systemd1 import Unit, Manager
    from pystemd import daemon
except ImportError:
    print("Requires: pip install pystemd")
    sys.exit(1)
# Setup logging to journal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('aios')
logger.addHandler(daemon.JournalHandler(SYSLOG_IDENTIFIER='aios'))
DB_PATH = Path('/var/lib/aios/aios.db')
UNIT_DIR = Path('/etc/systemd/system/')
class AIOSManager:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self.manager = Manager()
        self.manager.load()
        self.running = True
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        daemon.notify('READY=1')
        logger.info("AIOS Manager started")
    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                code TEXT NOT NULL,
                status TEXT DEFAULT 'proposed',  -- proposed, accepted, rejected
                scheduling TEXT,  -- OnCalendar format or none
                realtime_priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()
    def _handle_signal(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down")
        self.running = False
        daemon.notify('STOPPING=1')
    def propose_workflow(self, name, code, scheduling='none', realtime=0):
        self.conn.execute(
            "INSERT INTO workflows (name, code, scheduling, realtime_priority) VALUES (?, ?, ?, ?)",
            (name, code, scheduling, realtime)
        )
        self.conn.commit()
        logger.info(f"Proposed workflow: {name}")
    def review_workflows(self):
        return self.conn.execute(
            "SELECT id, name, code FROM workflows WHERE status = 'proposed'"
        ).fetchall()
    def accept_workflow(self, wf_id):
        wf = self.conn.execute(
            "SELECT * FROM workflows WHERE id = ? AND status = 'proposed'", (wf_id,)
        ).fetchone()
        if not wf:
            return False
        name, code, scheduling, realtime = wf['name'], wf['code'], wf['scheduling'], wf['realtime_priority']
        script_path = f"/opt/aios/{name}.py"
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        with open(script_path, 'w') as f:
            f.write(code)
        os.chmod(script_path, 0o755)
        service_name = f"aios-{name}.service"
        service_path = UNIT_DIR / service_name
        service_content = f"""[Unit]
Description=AIOS Workflow: {name}
After=network.target
[Service]
Type=notify
ExecStart=/usr/bin/python3 {script_path}
Restart=on-failure
StandardOutput=journal
StandardError=journal
KillMode=control-group
"""
        if realtime > 0:
            service_content += f"CPUSchedulingPolicy=rr\nCPUSchedulingPriority={realtime}\n"
        service_content += "[Install]\nWantedBy=multi-user.target\n"
        service_path.write_text(service_content)
        if scheduling != 'none':
            timer_name = f"aios-{name}.timer"
            timer_path = UNIT_DIR / timer_name
            timer_content = f"""[Unit]
Description=Timer for {name}
[Timer]
OnCalendar={scheduling}
Persistent=true
Unit={service_name}
[Install]
WantedBy=timers.target
"""
            timer_path.write_text(timer_content)
            self.manager.Reload()
            unit = Unit(timer_name.encode())
            unit.load()
            unit.Unit.Enable(b'true')
            unit.Unit.Start(b'replace')
        else:
            self.manager.Reload()
            unit = Unit(service_name.encode())
            unit.load()
            unit.Unit.Enable(b'true')
            unit.Unit.Start(b'replace')
        self.conn.execute(
            "UPDATE workflows SET status = 'accepted' WHERE id = ?", (wf_id,)
        )
        self.conn.commit()
        logger.info(f"Accepted and deployed: {name}")
        return True
    def reject_workflow(self, wf_id):
        self.conn.execute(
            "UPDATE workflows SET status = 'rejected' WHERE id = ?", (wf_id,)
        )
        self.conn.commit()
        logger.info(f"Rejected workflow ID: {wf_id}")
    def run(self):
        while self.running:
            print("\nAIOS Manager CLI:")
            print("1. Propose workflow")
            print("2. Review/Accept/Reject proposed")
            print("3. Exit")
            choice = input("Choice: ").strip()
            if choice == '1':
                name = input("Name: ").strip()
                code = input("Code (multi-line, end with EOF):\n")
                scheduling = input("Scheduling (e.g., '*-*-1 02:00:00' or 'none'): ").strip()
                realtime = int(input("Real-time priority (1-99, 0 for none): ").strip())
                self.propose_workflow(name, code, scheduling, realtime)
            elif choice == '2':
                wfs = self.review_workflows()
                if not wfs:
                    print("No proposed workflows.")
                    continue
                for wf in wfs:
                    print(f"ID: {wf['id']}, Name: {wf['name']}, Code: {wf['code']}")
                wf_id = int(input("ID to review: ").strip())
                action = input("Accept (a) or Reject (r)? ").strip().lower()
                if action == 'a':
                    self.accept_workflow(wf_id)
                elif action == 'r':
                    self.reject_workflow(wf_id)
            elif choice == '3':
                break
            time.sleep(0.1)  # Gentle poll
        logger.info("AIOS Manager shutdown")
if __name__ == "__main__":
    manager = AIOSManager()
    manager.run()