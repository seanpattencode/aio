#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime, timedelta

tasks = aios_db.read("tasks")
today = datetime.now().date()
plan = aios_db.read("daily_plan")

def is_pending(t):
    not_completed = not t.startswith("[x]")
    not_urgent = not t.startswith("[!]")
    return all([not_completed, not_urgent])

def print_task(t):
    print(f"- {t}")

pending = list(filter(is_pending, tasks))
plan[str(today)] = pending[:10]

aios_db.write("daily_plan", plan)
list(map(print_task, plan[str(today)]))