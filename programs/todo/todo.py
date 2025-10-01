#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime, timedelta
command = (sys.argv + ["list"])[1]
def get_tasks():
    return aios_db.read("tasks")
tasks = get_tasks()
def add_task():
    task_text = ' '.join(sys.argv[2:])
    task_desc = task_text.split('@')[0].strip()
    new_task = f"[ ] {datetime.now():%Y-%m-%d %H:%M} {task_desc}"
    aios_db.write("tasks", get_tasks() + [new_task])
    aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)", (f"Task: {task_desc}", datetime.now().isoformat(), "todo"))
def done_task():
    current_tasks = get_tasks()
    task_id = int(sys.argv[2]) - 1
    task = current_tasks[task_id]
    task_text = ' '.join(task.split()[3:])
    updated = list(current_tasks)
    updated[task_id] = task.replace("[ ]", "[x]")
    aios_db.write("tasks", updated)
    aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)", (f"Completed: {task_text}", datetime.now().isoformat(), "todo"))
def print_task(item):
    i, t = item
    print(f"{i+1}. {t}")
def list_tasks():
    list(map(print_task, enumerate(tasks)))
def is_not_done(t):
    return t.startswith("[x]") == False
def clear_done():
    return aios_db.write("tasks", list(filter(is_not_done, tasks)))
{"list": list_tasks, "add": add_task, "done": done_task, "clear": clear_done}.get(command, list_tasks)()