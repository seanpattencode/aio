#!/usr/bin/env python3
import sys
from datetime import datetime
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
command, get_tasks = (sys.argv + ["list"])[1], lambda: aios_db.read("tasks")
tasks = get_tasks()
commands = {
    "add": lambda: (aios_db.write("tasks", get_tasks() + [f"[ ] {datetime.now():%Y-%m-%d %H:%M} {' '.join(sys.argv[2:]).split('@')[0].strip()}"]),
                   aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)", (f"Task: {' '.join(sys.argv[2:]).split('@')[0].strip()}", datetime.now().isoformat(), "todo"))),
    "done": lambda: (lambda ts, tid, t: (aios_db.write("tasks", ts[:tid] + [t.replace("[ ]", "[x]")] + ts[tid+1:]),
                                          aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)", (f"Completed: {' '.join(t.split()[3:])}", datetime.now().isoformat(), "todo"))))(get_tasks(), int(sys.argv[2])-1, get_tasks()[int(sys.argv[2])-1]),
    "list": lambda: list(map(lambda x: print(f"{x[0]+1}. {x[1]}"), enumerate(tasks))),
    "clear": lambda: aios_db.write("tasks", [t for t in tasks if not t.startswith("[x]")])
}
commands.get(command, commands["list"])()