#!/usr/bin/env python3
import sys
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db

# Initialize services
aios_db.write("services", {})

# Parse arguments
s = aios_db.read("services")
c = (sys.argv + ["list"])[1]
n = (sys.argv + ["", None])[2]

# Define commands
def list_services():
    return list(map(print, [f"{k}: {v.get('status', 'unknown')}" for k, v in s.items()]))

def start_service():
    updated = {**s, n: {**s.get(n, {}), "status": "running"}}
    return aios_db.write("services", updated)

def stop_service():
    updated = {**s, n: {**s.get(n, {}), "status": "stopped"}}
    return aios_db.write("services", updated)

def get_status():
    if n == None:
        return print("specify service")
    return print(s.get(n, {}).get("status", "unknown"))

# Execute command
commands = {
    "list": list_services,
    "start": start_service,
    "stop": stop_service,
    "status": get_status
}

handler = commands.get(c, list_services)
handler()