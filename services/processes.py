#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import subprocess
import aios_db
import json
from pathlib import Path
from datetime import datetime

command = sys.argv[1] if len(sys.argv) > 1 else "json"
name = sys.argv[2] if len(sys.argv) > 2 else None

def get_all_processes():
    schedule = aios_db.read("schedule") or {}
    pids = aios_db.read("aios_pids") or {}
    python_files = list(Path('/home/seanpatten/projects/AIOS').rglob('*.py'))

    scheduled = sorted(
        [{"path": cmd, "type": "daily", "time": time, "status": "scheduled"} for time, cmd in schedule.get("daily", {}).items()] +
        [{"path": cmd, "type": "hourly", "time": f":{int(m):02d}", "status": "scheduled"} for m, cmd in schedule.get("hourly", {}).items()],
        key=lambda x: x["time"]
    )

    ongoing = [{"path": f"{k}_pid_{v}", "type": "running", "status": "active"} for k, v in pids.items()]

    core = [{"path": str(f.relative_to(Path('/home/seanpatten/projects/AIOS'))), "type": "file", "status": "available"}
            for f in python_files if 'archive' not in f.parts and '__pycache__' not in f.parts]

    return {"scheduled": scheduled, "ongoing": ongoing, "core": core}

actions = {
    "json": lambda: print(json.dumps(get_all_processes())),
    "list": lambda: [print(f"{p['path']}: {p['status']}") for cat in get_all_processes().values() for p in cat],
    "start": lambda: subprocess.Popen(['python3', name]) if name else None,
    "stop": lambda: subprocess.run(['pkill', '-f', name]) if name else None
}

actions.get(command, actions["json"])()