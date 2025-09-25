#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime

command = sys.argv[1] if len(sys.argv) > 1 else "list"

aios_db.execute("feed", "CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT, source TEXT, priority INTEGER DEFAULT 0)")

actions = {
    "add": lambda: aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)",
                                   (" ".join(sys.argv[2:]), datetime.now().isoformat(), "manual")),
    "list": lambda: [print(f"{row[3].split('T')[1][:5]} {row[1]}" if datetime.fromisoformat(row[2]).date() == datetime.now().date() else f"{row[2].split('T')[0]} {row[2].split('T')[1][:5]} {row[1]}")
                    for row in aios_db.query("feed", "SELECT id, content, timestamp, source FROM messages ORDER BY timestamp DESC LIMIT 50")],
    "view": lambda: [print(f"{datetime.fromisoformat(row[2]).strftime('%I:%M %p' if (aios_db.read('settings') or {}).get('time_format', '12h') == '12h' else '%H:%M')} {row[1]}"
                          if datetime.fromisoformat(row[2]).date() == datetime.now().date() else
                          f"{row[2].split('T')[0]} {datetime.fromisoformat(row[2]).strftime('%I:%M %p' if (aios_db.read('settings') or {}).get('time_format', '12h') == '12h' else '%H:%M')} {row[1]}")
                    for row in aios_db.query("feed", "SELECT id, content, timestamp, source FROM messages ORDER BY timestamp DESC LIMIT 50")],
    "clear": lambda: aios_db.execute("feed", "DELETE FROM messages WHERE timestamp < datetime('now', '-7 days')")
}

actions.get(command, actions["list"])()