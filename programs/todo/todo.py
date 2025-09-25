#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime, timedelta

tasks = aios_db.read("tasks") or []
command = sys.argv[1] if len(sys.argv) > 1 else "list"

def add_task():
    task_text = ' '.join(sys.argv[2:])
    deadline_parts = task_text.split('@')
    task_desc = deadline_parts[0].strip()
    deadline = datetime.now() + timedelta(hours=1)
    deadline_str = deadline_parts[1].strip() if len(deadline_parts) > 1 else None
    [[deadline := datetime.strptime(f"{datetime.now().date()} {deadline_str}", "%Y-%m-%d %H:%M")] if deadline_str and ':' in deadline_str else None]
    new_task = f"[ ] {datetime.now():%Y-%m-%d %H:%M} {task_desc}"
    aios_db.write("tasks", tasks + [new_task])
    aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)",
                    (f"Task: {task_desc} (Due: {deadline.strftime('%I:%M %p')})" if deadline_str else f"Task: {task_desc}",
                     deadline.isoformat() if deadline_str else datetime.now().isoformat(), "todo"))

def done_task():
    task_id = int(sys.argv[2]) - 1
    task = tasks[task_id]
    task_text = ' '.join(task.split()[3:])
    aios_db.write("tasks", [t.replace("[ ]", "[x]") if i == task_id else t for i, t in enumerate(tasks)])
    aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)",
                    (f"Completed: {task_text}", datetime.now().isoformat(), "todo"))

actions = {
    "list": lambda: [print(f"{i+1}. {t}") for i, t in enumerate(tasks)],
    "add": add_task,
    "done": done_task,
    "clear": lambda: aios_db.write("tasks", [t for t in tasks if not t.startswith("[x]")])
}

aios_db.execute("feed", "CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT, source TEXT, priority INTEGER DEFAULT 0)")
actions.get(command, actions["list"])()