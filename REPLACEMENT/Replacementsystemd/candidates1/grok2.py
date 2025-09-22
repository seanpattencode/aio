import sqlite3
import os
import subprocess
import signal
import sys
import time
import logging
from systemd import journal  # Requires python-systemd package
import sdnotify  # Requires sdnotify package

# Setup logging to journal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('aios_manager')
logger.addHandler(journal.JournalHandler(SYSLOG_IDENTIFIER='aios'))

DB_FILE = 'aios.db'
UNIT_DIR = '/etc/systemd/system/'  # System-wide; use ~/.config/systemd/user/ for user

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS workflows
                 (id INTEGER PRIMARY KEY, name TEXT, code TEXT, status TEXT, scheduling TEXT, realtime INTEGER)''')
    conn.commit()
    conn.close()

def propose_workflow(name, code, scheduling='none', realtime=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO workflows (name, code, status, scheduling, realtime) VALUES (?, ?, 'proposed', ?, ?)",
              (name, code, scheduling, realtime))
    conn.commit()
    conn.close()
    logger.info(f"Proposed workflow: {name}")

def review_workflows():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM workflows WHERE status = 'proposed'")
    return c.fetchall()

def accept_workflow(wf_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, code, scheduling, realtime FROM workflows WHERE id = ?", (wf_id,))
    wf = c.fetchone()
    if wf:
        name, code, scheduling, realtime = wf
        # Write code to file
        script_path = f"/opt/aios/{name}.py"
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        with open(script_path, 'w') as f:
            f.write(code)
        os.chmod(script_path, 0o755)
        # Create unit file
        unit_file = f"{UNIT_DIR}{name}.service"
        with open(unit_file, 'w') as f:
            f.write(f"""[Unit]
Description=AIOS Workflow: {name}
After=network.target

[Service]
ExecStart=/usr/bin/python3 {script_path}
User=root
Type=notify
Restart=on-failure
CPUSchedulingPolicy=rr
CPUSchedulingPriority={realtime if realtime else 50}

[Install]
WantedBy=multi-user.target
""")
        # If scheduling, create timer
        if scheduling != 'none':
            timer_file = f"{UNIT_DIR}{name}.timer"
            with open(timer_file, 'w') as f:
                f.write(f"""[Unit]
Description=Timer for {name}

[Timer]
OnCalendar={scheduling}
Persistent=true

[Install]
WantedBy=timers.target
""")
            subprocess.run(['systemctl', 'enable', f"{name}.timer"])
        subprocess.run(['systemctl', 'daemon-reload'])
        subprocess.run(['systemctl', 'enable', f"{name}.service"])
        subprocess.run(['systemctl', 'start', f"{name}.service"])
        c.execute("UPDATE workflows SET status = 'accepted' WHERE id = ?", (wf_id,))
        conn.commit()
        logger.info(f"Accepted and started: {name}")
    conn.close()

def reject_workflow(wf_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE workflows SET status = 'rejected' WHERE id = ?", (wf_id,))
    conn.commit()
    conn.close()
    logger.info(f"Rejected workflow ID: {wf_id}")

def reap_children():
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            logger.info(f"Reaped child {pid}")
        except ChildProcessError:
            break

def handle_signals(signum, frame):
    logger.info("Shutting down...")
    reap_children()
    sys.exit(0)

def main():
    init_db()
    signal.signal(signal.SIGTERM, handle_signals)
    signal.signal(signal.SIGINT, handle_signals)
    n = sdnotify.SystemdNotifier()
    n.notify("READY=1")

    while True:
        print("\nAIOS Manager: 1=Propose, 2=Review/Accept/Reject, 3=Exit")
        choice = input("Choice: ")
        if choice == '1':
            name = input("Name: ")
            code = input("Code (multi-line, end with EOF): ")
            scheduling = input("Scheduling (e.g., '*-*-1 02:00:00' or 'none'): ")
            realtime = int(input("Real-time priority (1-99, 0 for none): "))
            propose_workflow(name, code, scheduling, realtime)
        elif choice == '2':
            wfs = review_workflows()
            for wf in wfs:
                print(f"ID: {wf[0]}, Name: {wf[1]}, Code: {wf[2]}")
            wf_id = int(input("ID to accept/reject: "))
            action = input("Accept (a) or Reject (r)? ")
            if action == 'a':
                accept_workflow(wf_id)
            elif action == 'r':
                reject_workflow(wf_id)
        elif choice == '3':
            break
        time.sleep(1)  # Poll gently
        reap_children()  # Reap any children

if __name__ == "__main__":
    main()