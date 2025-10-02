#!/usr/bin/env python3
import sys, subprocess, schedule as sched
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
schedules = aios_db.read("schedule")
run_cmd = lambda cmd: subprocess.run(cmd, shell=True, timeout=300)
list(map(lambda item: sched.every().day.at(item[0]).do(run_cmd, item[1]), schedules.get("daily", {}).items()))
list(map(lambda item: sched.every().hour.at(f":{int(item[0]):02d}").do(run_cmd, item[1]), schedules.get("hourly", {}).items()))
sched.run_pending()