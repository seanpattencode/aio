#!/usr/bin/env python3
import sys
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db
from datetime import datetime

c = (sys.argv + ["list"])[1]

print_msg = lambda r: print({True: f"{r[2].split('T')[1][:5]} {r[1]}", False: f"{r[2].split('T')[0]} {r[2].split('T')[1][:5]} {r[1]}"}[datetime.fromisoformat(r[2]).date() == datetime.now().date()])

commands = {
    "add": lambda: aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)", (" ".join(sys.argv[2:]), datetime.now().isoformat(), "manual")),
    "list": lambda: list(map(print_msg, aios_db.query("feed", "SELECT id, content, timestamp, source FROM messages ORDER BY timestamp DESC LIMIT 50"))),
    "view": lambda: list(map(print_msg, aios_db.query("feed", "SELECT id, content, timestamp, source FROM messages ORDER BY timestamp DESC LIMIT 50"))),
    "clear": lambda: aios_db.execute("feed", "DELETE FROM messages WHERE timestamp < datetime('now', '-7 days')")
}

commands[c]()