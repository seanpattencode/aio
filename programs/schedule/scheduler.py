#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import schedule as sched
import subprocess
import aios_db

schedules = aios_db.read("schedule")

[sched.every().day.at(t).do(lambda c=cmd: subprocess.run(c, shell=True))
 for t, cmd in schedules.get("daily", {}).items()]

[sched.every().hour.at(f":{int(m):02d}").do(lambda c=cmd: subprocess.run(c, shell=True))
 for m, cmd in schedules.get("hourly", {}).items()]

sched.run_pending()