#!/usr/bin/env python3
import sys, subprocess, json
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from pathlib import Path
command = (sys.argv + ["json"])[1]
name = (sys.argv + ["", None])[2]
def get_time(x):
    return x["time"]
def is_not_archive(f):
    return ('archive' not in f.parts) * ('__pycache__' not in f.parts)
def get_all_processes():
    aios_db.write("schedule", {})
    aios_db.write("aios_pids", {})
    schedule = aios_db.read("schedule")
    pids = aios_db.read("aios_pids")
    python_files = list(Path('/home/seanpatten/projects/AIOS').rglob('*.py'))
    scheduled = sorted([{"path": cmd, "type": "daily", "time": time, "status": "scheduled"} for time, cmd in schedule.get("daily", {}).items()] + [{"path": cmd, "type": "hourly", "time": f":{int(m):02d}", "status": "scheduled"} for m, cmd in schedule.get("hourly", {}).items()], key=get_time)
    ongoing = [{"path": f"{k}_pid_{v}", "type": "running", "status": "active"} for k, v in pids.items()]
    core = [{"path": str(f.relative_to(Path('/home/seanpatten/projects/AIOS'))), "type": "file", "status": "available"} for f in python_files]
    return {"scheduled": scheduled, "ongoing": ongoing, "core": core}
def cmd_json():
    print(json.dumps(get_all_processes()))
def print_process(p):
    print(f"{p['path']}: {p['status']}")
def cmd_list():
    all_procs = get_all_processes()
    list(map(print_process, all_procs.get("scheduled", [])))
    list(map(print_process, all_procs.get("ongoing", [])))
    list(map(print_process, all_procs.get("core", [])))
def cmd_start():
    {True: None, False: subprocess.Popen(['python3', name])}[name == None]
def cmd_stop():
    {True: None, False: subprocess.run(['pkill', '-f', name], timeout=5)}[name == None]
{"json": cmd_json, "list": cmd_list, "start": cmd_start, "stop": cmd_stop}.get(command, cmd_json)()