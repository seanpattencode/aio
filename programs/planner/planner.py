#!/usr/bin/env python3
import sys
from datetime import datetime
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
aios_db.write("tasks", []) or aios_db.write("daily_plan", {})
tasks, today, plan = aios_db.read("tasks"), str(datetime.now().date()), aios_db.read("daily_plan")
pending = [t for t in tasks if not (t.startswith("[x]") or t.startswith("[!]"))][:10]
plan[today] = pending
aios_db.write("daily_plan", plan)
list(map(lambda t: print(f"- {t}"), pending))