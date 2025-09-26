#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
import json
import subprocess
from datetime import datetime

command = sys.argv[1] if len(sys.argv) > 1 else "json"

def get_jobs():
    jobs = aios_db.read("jobs") or {"done": [], "ongoing": [], "scheduled": []}
    schedule = aios_db.read("schedule") or {}
    scheduled_jobs = []
    [[scheduled_jobs.append(f"Daily {t}: {c}")] for t,c in sorted(schedule.get("daily",{}).items())]
    [[scheduled_jobs.append(f"Hourly :{int(m):02d}: {c}")] for m,c in sorted(schedule.get("hourly",{}).items(), key=lambda x: int(x[0]))]
    return {**jobs, "scheduled": scheduled_jobs}

actions = {
    "json": lambda: print(json.dumps(get_jobs())),
    "list": lambda: [[print(f"Done: {j}")] for j in get_jobs().get("done", [])] + [[print(f"Ongoing: {j}")] for j in get_jobs().get("ongoing", [])] + [[print(f"Scheduled: {j}")] for j in get_jobs().get("scheduled", [])],
    "done": lambda: aios_db.write("jobs", {**get_jobs(), "done": get_jobs().get("done", []) + [" ".join(sys.argv[2:])], "ongoing": [j for j in get_jobs().get("ongoing", []) if j != " ".join(sys.argv[2:])]}),
    "start": lambda: aios_db.write("jobs", {**get_jobs(), "ongoing": get_jobs().get("ongoing", []) + [" ".join(sys.argv[2:])]}),
    "clear": lambda: aios_db.write("jobs", {**get_jobs(), "done": []})
}

actions.get(command, actions["json"])()