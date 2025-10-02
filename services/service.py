#!/usr/bin/env python3
import sys
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db

aios_db.write("services", {})
s = aios_db.read("services")
c = (sys.argv + ["list"])[1]
n = (sys.argv + ["", ""])[2]

commands = {
    "list": lambda: list(map(print, [f"{k}: {v.get('status', 'unknown')}" for k, v in s.items()])),
    "start": lambda: aios_db.write("services", {**s, n: {**s.get(n, {}), "status": "running"}}),
    "stop": lambda: aios_db.write("services", {**s, n: {**s.get(n, {}), "status": "stopped"}}),
    "status": lambda: print(s.get(n, {}).get("status", "unknown") or "specify service")
}

commands[c]()