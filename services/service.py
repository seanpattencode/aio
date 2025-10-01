#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
aios_db.write("services", {})
services = aios_db.read("services")
command = (sys.argv + ["list"])[1]
name = (sys.argv + ["", None])[2]
def cmd_list():
    list(map(print, [f"{k}: {v.get('status', 'unknown')}" for k, v in services.items()]))
def cmd_start():
    aios_db.write("services", {**services, name: {**services.get(name, {}), "status": "running"}})
def cmd_stop():
    aios_db.write("services", {**services, name: {**services.get(name, {}), "status": "stopped"}})
def cmd_status():
    print({True: "specify service", False: services.get(name, {}).get("status", "unknown")}[name == None])
{"list": cmd_list, "start": cmd_start, "stop": cmd_stop, "status": cmd_status}.get(command, cmd_list)()