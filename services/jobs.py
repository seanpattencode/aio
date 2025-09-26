#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
import aios_db
import json

cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
arg = ' '.join(sys.argv[2:])
data = aios_db.read("jobs") or {}
store = {"active": data.get("active", data.get("tasks", [])), "done": data.get("done", [])}

print(json.dumps(store)) if cmd == "json" else None
print('\n'.join(store["active"] + ["\n=== Completed ==="] + store["done"]) if store["done"] else '\n'.join(store["active"])) if cmd == "list" else None
aios_db.write("jobs", {"active": store["active"] + [arg], "done": store["done"]}) if cmd == "add" and arg else None
aios_db.write("jobs", {"active": [t for t in store["active"] if t != arg] + store["done"], "done": []}) if cmd == "redo" and arg in store["done"] else None
aios_db.write("jobs", {"active": [t for t in store["active"] if t != arg], "done": store["done"] + [arg]}) if cmd == "done" and arg else None
aios_db.write("jobs", {"active": [t for t in store["active"] if t != arg], "done": store["done"]}) if cmd == "dismiss" and arg else None
aios_db.write("jobs", {"active": store["active"], "done": []}) if cmd == "clear" else None