#!/usr/bin/env python3
import sys, subprocess, json
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db
from pathlib import Path

# Parse arguments
c = (sys.argv + ["json"])[1]
n = (sys.argv + ["", None])[2]

# Initialize database entries
[aios_db.write(k, v) for k, v in [("schedule", {}), ("aios_pids", {})]]

def get_all_processes():
    """Get all process information"""
    schedule = aios_db.read("schedule")
    pids = aios_db.read("aios_pids")
    aios_path = Path('/home/seanpatten/projects/AIOS')

    # Build scheduled tasks
    daily_tasks = [{"path": cmd, "type": "daily", "time": time, "status": "scheduled"}
                   for time, cmd in schedule.get("daily", {}).items()]

    hourly_tasks = [{"path": cmd, "type": "hourly", "time": f":{int(m):02d}", "status": "scheduled"}
                    for m, cmd in schedule.get("hourly", {}).items()]

    scheduled = sorted(daily_tasks + hourly_tasks, key=lambda x: x["time"])

    # Build ongoing processes
    ongoing = [{"path": f"{k}_pid_{v}", "type": "running", "status": "active"}
               for k, v in pids.items()]

    # Build core files list
    py_files = aios_path.rglob('*.py')
    core = []
    for f in py_files:
        if 'archive' not in f.parts and '__pycache__' not in f.parts:
            core.append({
                "path": str(f.relative_to(aios_path)),
                "type": "file",
                "status": "available"
            })

    return {
        "scheduled": scheduled,
        "ongoing": ongoing,
        "core": core
    }

def print_process(p):
    """Print a single process"""
    print(f"{p['path']}: {p['status']}")

def cmd_json():
    """Output JSON format"""
    print(json.dumps(get_all_processes()))

def cmd_list():
    """List all processes"""
    ap = get_all_processes()
    list(map(print_process, ap.get("scheduled", [])))
    list(map(print_process, ap.get("ongoing", [])))
    list(map(print_process, ap.get("core", [])))

def cmd_start():
    """Start a process"""
    if n is not None:
        subprocess.Popen(['python3', n])

def cmd_stop():
    """Stop a process"""
    if n is not None:
        subprocess.run(['pkill', '-f', n], timeout=5)

# Command dispatch
commands = {
    "json": cmd_json,
    "list": cmd_list,
    "start": cmd_start,
    "stop": cmd_stop
}

# Execute command (default to json)
handler = commands.get(c, cmd_json)
handler()