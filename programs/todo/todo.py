#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime, timedelta

tasks = aios_db.read("tasks")
command = (sys.argv + ["list"])[1]

def add_task():
    task_text = ' '.join(sys.argv[2:])
    deadline_parts = task_text.split('@')
    task_desc = deadline_parts[0].strip()
    deadline = datetime.now() + timedelta(hours=1)
    deadline_str = (deadline_parts + [""])[1].strip()
    deadline_str and ':' in deadline_str and setattr(sys.modules[__name__], 'deadline', datetime.strptime(f"{datetime.now().date()} {deadline_str}", "%Y-%m-%d %H:%M"))
    new_task = f"[ ] {datetime.now():%Y-%m-%d %H:%M} {task_desc}"
    aios_db.write("tasks", tasks + [new_task])
    aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)",
                    (deadline_str and f"Task: {task_desc} (Due: {deadline.strftime('%I:%M %p')})" or f"Task: {task_desc}",
                     deadline_str and deadline.isoformat() or datetime.now().isoformat(), "todo"))

def done_task():
    task_id = int(sys.argv[2]) - 1
    task = tasks[task_id]
    task_text = ' '.join(task.split()[3:])
    updated = list(tasks)
    updated[task_id] = task.replace("[ ]", "[x]")
    aios_db.write("tasks", updated)
    aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)",
                    (f"Completed: {task_text}", datetime.now().isoformat(), "todo"))

def print_task(item):
    i, t = item
    print(f"{i+1}. {t}")

def list_tasks():
    list(map(print_task, enumerate(tasks)))

def is_not_done(t):
    return not t.startswith("[x]")

def clear_done():
    return aios_db.write("tasks", list(filter(is_not_done, tasks)))

actions = {
    "list": list_tasks,
    "add": add_task,
    "done": done_task,
    "clear": clear_done
}

aios_db.execute("feed", "CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT, source TEXT, priority INTEGER DEFAULT 0)")
actions.get(command, actions["list"])()