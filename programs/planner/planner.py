#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime
aios_db.write("tasks", [])
aios_db.write("daily_plan", {})
tasks = aios_db.read("tasks")
today = datetime.now().date()
plan = aios_db.read("daily_plan")
def is_pending(t):
    return (t.startswith("[x]") == False) * (t.startswith("[!]") == False)
def print_task(t):
    print(f"- {t}")
pending = list(filter(is_pending, tasks))
plan[str(today)] = pending[:10]
aios_db.write("daily_plan", plan)
list(map(print_task, plan[str(today)]))