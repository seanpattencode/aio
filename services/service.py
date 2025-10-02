#!/usr/bin/env python3
import sys
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db
aios_db.write("services", {})
s, c, n = aios_db.read("services"), (sys.argv + ["list"])[1], (sys.argv + ["", None])[2]
{"list": lambda: list(map(print, [f"{k}: {v.get('status', 'unknown')}" for k, v in s.items()])), "start": lambda: aios_db.write("services", {**s, n: {**s.get(n, {}), "status": "running"}}), "stop": lambda: aios_db.write("services", {**s, n: {**s.get(n, {}), "status": "stopped"}}), "status": lambda: print({True: "specify service", False: s.get(n, {}).get("status", "unknown")}[n == None])}.get(c, lambda: list(map(print, [f"{k}: {v.get('status', 'unknown')}" for k, v in s.items()])))()