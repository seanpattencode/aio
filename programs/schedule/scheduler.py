#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import schedule as sched
import subprocess
import aios_db

schedules = aios_db.read("schedule")

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True)

def schedule_daily(item):
    t, cmd = item
    sched.every().day.at(t).do(run_cmd, cmd)

def schedule_hourly(item):
    m, cmd = item
    sched.every().hour.at(f":{int(m):02d}").do(run_cmd, cmd)

list(map(schedule_daily, schedules.get("daily", {}).items()))
list(map(schedule_hourly, schedules.get("hourly", {}).items()))

sched.run_pending()