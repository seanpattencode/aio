#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import subprocess
import aios_db
import os
import signal

command = sys.argv[1] if len(sys.argv) > 1 else "list"
name = sys.argv[2] if len(sys.argv) > 2 else None

def get_processes():
    services = aios_db.read("services") or {}
    schedule = aios_db.read("schedule") or {}
    pids = aios_db.read("aios_pids") or {}
    processes = []

    [[processes.append({"name": k, "status": v.get("status", "unknown"), "type": "service", "next": None})]
     for k, v in services.items()]

    [[processes.append({"name": f"{cmd} @ {time}", "status": "scheduled", "type": "daily", "next": time})]
     for time, cmd in schedule.get("daily", {}).items()]

    [[processes.append({"name": f"{cmd} @ :{int(minute):02d}", "status": "scheduled", "type": "hourly", "next": f":{int(minute):02d}"})]
     for minute, cmd in schedule.get("hourly", {}).items()]

    return sorted([p for p in processes if p["type"] in ["daily", "hourly"]], key=lambda x: x["next"] or "") + \
           [p for p in processes if p["type"] == "service"]

actions = {
    "list": lambda: [print(f"{p['name']}: {p['status']}") for p in get_processes()],
    "start": lambda: aios_db.write("services", {**aios_db.read("services") or {}, name: {"status": "running"}}),
    "stop": lambda: aios_db.write("services", {**aios_db.read("services") or {}, name: {"status": "stopped"}}),
    "restart": lambda: [actions["stop"](), actions["start"]()]
}

actions.get(command, actions["list"])()