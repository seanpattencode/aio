#!/usr/bin/env python3
import sys, subprocess, json
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db
from pathlib import Path
c, n = (sys.argv + ["json"])[1], (sys.argv + ["", None])[2]
[aios_db.write(k, v) for k, v in [("schedule", {}), ("aios_pids", {})]]
gap = lambda: (lambda s: {"scheduled": sorted([{"path": cmd, "type": "daily", "time": time, "status": "scheduled"} for time, cmd in s.get("daily", {}).items()] + [{"path": cmd, "type": "hourly", "time": f":{int(m):02d}", "status": "scheduled"} for m, cmd in s.get("hourly", {}).items()], key=lambda x: x["time"]), "ongoing": [{"path": f"{k}_pid_{v}", "type": "running", "status": "active"} for k, v in aios_db.read("aios_pids").items()], "core": [{"path": str(f.relative_to(Path('/home/seanpatten/projects/AIOS'))), "type": "file", "status": "available"} for f in list(Path('/home/seanpatten/projects/AIOS').rglob('*.py')) if ('archive' not in f.parts) * ('__pycache__' not in f.parts)]})(aios_db.read("schedule"))
pp = lambda p: print(f"{p['path']}: {p['status']}")
{"json": lambda: print(json.dumps(gap())), "list": lambda: (lambda ap: (list(map(pp, ap.get("scheduled", []))), list(map(pp, ap.get("ongoing", []))), list(map(pp, ap.get("core", []))))[-1])(gap()), "start": lambda: {True: None, False: subprocess.Popen(['python3', n])}[n == None], "stop": lambda: {True: None, False: subprocess.run(['pkill', '-f', n], timeout=5)}[n == None]}.get(c, lambda: print(json.dumps(gap())))()