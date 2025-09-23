#!/usr/bin/env python3

import sqlite3
import os
import sys
import dbus
import argparse
import uuid
import subprocess

DB_PATH = 'aios.db'
UNIT_DIR = '/etc/systemd/system/'  # Or user dir for non-root
SYSTEMD_BUS = dbus.SystemBus()
SYSTEMD_OBJ = SYSTEMD_BUS.get_object('org.freedesktop.systemd1', '/org/freedesktop/systemd1')
MANAGER = dbus.Interface(SYSTEMD_OBJ, 'org.freedesktop.systemd1.Manager')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS workflows
                 (id TEXT PRIMARY KEY, name TEXT, script_code TEXT, status TEXT, schedule TEXT, rt_priority INTEGER)''')
    conn.commit()
    conn.close()

def add_proposed_workflow(name, script_code, schedule=None, rt_priority=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    wf_id = str(uuid.uuid4())
    c.execute("INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?)",
              (wf_id, name, script_code, 'proposed', schedule, rt_priority))
    conn.commit()
    conn.close()
    print(f"Proposed workflow {name} added with ID {wf_id}")

def list_workflows(status=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = "SELECT id, name, status FROM workflows"
    if status:
        query += f" WHERE status = '{status}'"
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return rows

def review_workflow(wf_id, action):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM workflows WHERE id = ?", (wf_id,))
    wf = c.fetchone()
    if not wf:
        print("Workflow not found")
        return
    if action == 'accept':
        c.execute("UPDATE workflows SET status = 'approved' WHERE id = ?", (wf_id,))
        conn.commit()
        deploy_workflow(wf)
    elif action == 'reject':
        c.execute("DELETE FROM workflows WHERE id = ?", (wf_id,))
        conn.commit()
        print(f"Workflow {wf_id} rejected and deleted")
    conn.close()

def deploy_workflow(wf):
    wf_id, name, script_code, _, schedule, rt_priority = wf
    script_path = f"/tmp/{wf_id}.py"
    with open(script_path, 'w') as f:
        f.write(script_code)
    os.chmod(script_path, 0o755)

    service_name = f"aios-{wf_id}.service"
    service_path = os.path.join(UNIT_DIR, service_name)
    with open(service_path, 'w') as f:
        f.write(f"""[Unit]
Description=AIOS Workflow {name}

[Service]
Type=notify
ExecStart=/usr/bin/python3 {script_path}
Restart=on-failure
Environment=PYTHONUNBUFFERED=1
""")
        if rt_priority:
            f.write(f"CPUSchedulingPolicy=rr\nCPUSchedulingPriority={rt_priority}\nCPUSchedulingResetOnFork=true\n")

    if schedule:
        timer_name = f"aios-{wf_id}.timer"
        timer_path = os.path.join(UNIT_DIR, timer_name)
        with open(timer_path, 'w') as f:
            f.write(f"""[Unit]
Description=Timer for AIOS Workflow {name}

[Timer]
OnCalendar={schedule}  # e.g., '*-*-* *:0/30:00' for every 30 min

[Install]
WantedBy=timers.target
""")
        subprocess.run(['systemctl', 'daemon-reload'])
        MANAGER.EnableUnitFiles([timer_name], False, True)
        MANAGER.StartUnit(timer_name, 'replace')
    else:
        subprocess.run(['systemctl', 'daemon-reload'])
        MANAGER.EnableUnitFiles([service_name], False, True)
        MANAGER.StartUnit(service_name, 'replace')

    print(f"Workflow {wf_id} deployed")

def manage_workflow(wf_id, command):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status FROM workflows WHERE id = ?", (wf_id,))
    status = c.fetchone()
    conn.close()
    if not status or status[0] != 'approved':
        print("Only approved workflows can be managed")
        return

    service_name = f"aios-{wf_id}.service"
    if command == 'stop':
        MANAGER.StopUnit(service_name, 'replace')
    elif command == 'restart':
        MANAGER.RestartUnit(service_name, 'replace')
    elif command == 'status':
        unit = MANAGER.GetUnit(service_name)
        prop = dbus.Interface(SYSTEMD_BUS.get_object('org.freedesktop.systemd1', unit), 'org.freedesktop.DBus.Properties')
        print(prop.Get('org.freedesktop.systemd1.Unit', 'ActiveState'))

if __name__ == '__main__':
    init_db()
    parser = argparse.ArgumentParser(description='AIOS Workflow Manager')
    subparsers = parser.add_subparsers(dest='cmd')

    add = subparsers.add_parser('add', help='Add proposed workflow')
    add.add_argument('name')
    add.add_argument('script_file', help='Path to script code file')
    add.add_argument('--schedule', help='systemd OnCalendar format')
    add.add_argument('--rt_priority', type=int, help='Real-time priority 1-99')

    list_cmd = subparsers.add_parser('list', help='List workflows')
    list_cmd.add_argument('--status', help='Filter by status')

    review = subparsers.add_parser('review', help='Review workflow')
    review.add_argument('wf_id')
    review.add_argument('action', choices=['accept', 'reject'])

    manage = subparsers.add_parser('manage', help='Manage approved workflow')
    manage.add_argument('wf_id')
    manage.add_argument('command', choices=['stop', 'restart', 'status'])

    args = parser.parse_args()

    if args.cmd == 'add':
        with open(args.script_file, 'r') as f:
            code = f.read()
        add_proposed_workflow(args.name, code, args.schedule, args.rt_priority)
    elif args.cmd == 'list':
        for row in list_workflows(args.status):
            print(row)
    elif args.cmd == 'review':
        review_workflow(args.wf_id, args.action)
    elif args.cmd == 'manage':
        manage_workflow(args.wf_id, args.command)
    else:
        parser.print_help()