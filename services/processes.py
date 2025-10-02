#!/usr/bin/env python3
import sys, subprocess, json
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db
from pathlib import Path

c = (sys.argv + ["json"])[1]
n = (sys.argv + ["", ""])[2]

[aios_db.write(k, v) for k, v in [("schedule", {}), ("aios_pids", {})]]

get_procs = lambda: {
    "scheduled": sorted(
        [{"path": cmd, "type": "daily", "time": time, "status": "scheduled"} for time, cmd in aios_db.read("schedule").get("daily", {}).items()] +
        [{"path": cmd, "type": "hourly", "time": f":{int(m):02d}", "status": "scheduled"} for m, cmd in aios_db.read("schedule").get("hourly", {}).items()],
        key=lambda x: x["time"]
    ),
    "ongoing": [{"path": f"{k}_pid_{v}", "type": "running", "status": "active"} for k, v in aios_db.read("aios_pids").items()],
    "core": [{"path": str(f.relative_to(Path('/home/seanpatten/projects/AIOS'))), "type": "file", "status": "available"}
             for f in list(filter(lambda f: 'archive' not in f.parts and '__pycache__' not in f.parts, Path('/home/seanpatten/projects/AIOS').rglob('*.py')))]
}

print_proc = lambda p: print(f"{p['path']}: {p['status']}")

commands = {
    "json": lambda: print(json.dumps(get_procs())),
    "list": lambda: (list(map(print_proc, get_procs()["scheduled"])), list(map(print_proc, get_procs()["ongoing"])), list(map(print_proc, get_procs()["core"])))[0],
    "start": lambda: subprocess.Popen(['python3', n]) or None,
    "stop": lambda: subprocess.run(['pkill', '-f', n], timeout=5) or None
}

commands[c]()