#!/usr/bin/env python3
import sys
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db
from datetime import datetime

# Get command
c = (sys.argv + ["list"])[1]

# Message formatting functions
def print_message(r):
    """Print message with standard formatting"""
    is_today = datetime.fromisoformat(r[2]).date() == datetime.now().date()
    time_part = r[2].split('T')[1][:5]

    if is_today:
        print(f"{time_part} {r[1]}")
    else:
        date_part = r[2].split('T')[0]
        print(f"{date_part} {time_part} {r[1]}")

def print_message_with_format(r, time_format):
    """Print message with custom time format"""
    dt = datetime.fromisoformat(r[2])
    is_today = dt.date() == datetime.now().date()
    time_str = dt.strftime(time_format)

    if is_today:
        print(f"{time_str} {r[1]}")
    else:
        date_part = r[2].split('T')[0]
        print(f"{date_part} {time_str} {r[1]}")

# Command functions
def add_message():
    content = " ".join(sys.argv[2:])
    timestamp = datetime.now().isoformat()
    aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)",
                   (content, timestamp, "manual"))

def list_messages():
    messages = aios_db.query("feed",
                            "SELECT id, content, timestamp, source FROM messages "
                            "ORDER BY timestamp DESC LIMIT 50")
    list(map(print_message, messages))

def view_messages():
    aios_db.write('settings', {})
    settings = aios_db.read('settings')
    is_12h = settings.get('time_format', '12h') == '12h'
    time_format = '%I:%M %p' if is_12h else '%H:%M'

    messages = aios_db.query("feed",
                            "SELECT id, content, timestamp, source FROM messages "
                            "ORDER BY timestamp DESC LIMIT 50")
    list(map(lambda r: print_message_with_format(r, time_format), messages))

def clear_old_messages():
    aios_db.execute("feed", "DELETE FROM messages WHERE timestamp < datetime('now', '-7 days')")

# Command dispatch
commands = {
    "add": add_message,
    "list": list_messages,
    "view": view_messages,
    "clear": clear_old_messages
}

# Execute command (default to list)
handler = commands.get(c, list_messages)
handler()