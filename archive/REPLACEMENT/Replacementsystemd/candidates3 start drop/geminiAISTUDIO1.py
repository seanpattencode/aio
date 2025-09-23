#!/usr/bin/env python3
import sqlite3
import subprocess
import os

DB_PATH = "/var/lib/aios/workflows.db"
SYSTEMD_USER_PATH = os.path.expanduser("~/.config/systemd/user/")

def setup_database():
    """Initializes the SQLite database and table if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            command TEXT NOT NULL,
            schedule TEXT, -- e.g., '*-*-* 02:00:00' for daily at 2 AM
            realtime BOOLEAN DEFAULT 0,
            priority INTEGER DEFAULT 50, -- Real-time priority (1-99)
            cpu_weight INTEGER DEFAULT 1024, -- Non-real-time CPU shares
            memory_max_mb INTEGER -- Max memory in MB
        )
    ''')
    conn.commit()
    conn.close()

def create_systemd_service(workflow):
    """Generates and writes a systemd .service file for a workflow."""
    service_content = f"""[Unit]
Description=AIOS Workflow: {workflow['name']}

[Service]
Type=simple
ExecStart={workflow['command']}
Restart=on-failure
"""
    if workflow['realtime']:
        service_content += f"CPUSchedulingPolicy=fifo\n"
        service_content += f"CPUSchedulingPriority={workflow['priority']}\n"
    else:
        service_content += f"CPUWeight={workflow['cpu_weight']}\n"

    if workflow['memory_max_mb']:
        service_content += f"MemoryMax={workflow['memory_max_mb']}M\n"

    service_content += "\n[Install]\nWantedBy=default.target\n"
    
    service_file_path = os.path.join(SYSTEMD_USER_PATH, f"{workflow['name']}.service")
    os.makedirs(SYSTEMD_USER_PATH, exist_ok=True)
    with open(service_file_path, "w") as f:
        f.write(service_content)
    return service_file_path

def create_systemd_timer(workflow):
    """Generates and writes a systemd .timer file for a scheduled workflow."""
    if not workflow.get('schedule'):
        return None
        
    timer_content = f"""[Unit]
Description=Timer for AIOS Workflow: {workflow['name']}

[Timer]
OnCalendar={workflow['schedule']}
Persistent=true

[Install]
WantedBy=timers.target
"""
    timer_file_path = os.path.join(SYSTEMD_USER_PATH, f"{workflow['name']}.timer")
    with open(timer_file_path, "w") as f:
        f.write(timer_content)
    return timer_file_path

def run_systemctl(command, unit_name):
    """Helper function to run systemctl commands for the user session."""
    try:
        subprocess.run(["systemctl", "--user"] + command + [unit_name], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing systemctl command: {e}")

def add_and_enable_workflow(workflow_details):
    """Adds a workflow to the DB and creates/enables the systemd units."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO workflows (name, command, schedule, realtime, priority, cpu_weight, memory_max_mb) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            workflow_details['name'], workflow_details['command'],
            workflow_details.get('schedule'), workflow_details.get('realtime', 0),
            workflow_details.get('priority', 50), workflow_details.get('cpu_weight', 1024),
            workflow_details.get('memory_max_mb')
        )
    )
    conn.commit()
    conn.close()

    create_systemd_service(workflow_details)
    run_systemctl(["daemon-reload"], "")

    if workflow_details.get('schedule'):
        create_systemd_timer(workflow_details)
        run_systemctl(["enable", "--now"], f"{workflow_details['name']}.timer")
        print(f"Enabled and started timer for scheduled workflow: {workflow_details['name']}")
    else:
        run_systemctl(["enable", "--now"], f"{workflow_details['name']}.service")
        print(f"Enabled and started on-demand workflow: {workflow_details['name']}")

if __name__ == "__main__":
    setup_database()

    # Example: Add a standard, on-demand AI workflow for data processing
    data_processing_workflow = {
        "name": "aios-data-processor",
        "command": "/usr/bin/python3 -c 'import time; print(\"Processing data...\"); time.sleep(10)'",
        "memory_max_mb": 512
    }
    #add_and_enable_workflow(data_processing_workflow)

    # Example: Add a scheduled, daily reporting workflow
    reporting_workflow = {
        "name": "aios-daily-report",
        "command": "/usr/bin/python3 -c 'print(\"Generating daily report...\")'",
        "schedule": "*-*-* 03:00:00",
        "cpu_weight": 512
    }
    #add_and_enable_workflow(reporting_workflow)
    
    # Example: Add a real-time inference workflow
    inference_workflow = {
        "name": "aios-realtime-inference",
        "command": "/usr/bin/python3 /opt/aios/inference_server.py",
        "realtime": True,
        "priority": 90
    }
    #add_and_enable_workflow(inference_workflow)

    print("\nAIOS Manager setup complete. Check systemctl --user status for workflow status.")
    # To see the status of a service: systemctl --user status aios-data-processor.service
    # To see the status of a timer: systemctl --user list-timers