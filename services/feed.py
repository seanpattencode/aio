#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime
command = (sys.argv + ["list"])[1]
def cmd_add():
    aios_db.execute("feed", "INSERT INTO messages(content, timestamp, source) VALUES (?, ?, ?)", (" ".join(sys.argv[2:]), datetime.now().isoformat(), "manual"))
def print_message(row):
    time_part = row[2].split('T')[1][:5]
    date_part = row[2].split('T')[0]
    print({True: f"{time_part} {row[1]}", False: f"{date_part} {time_part} {row[1]}"}[datetime.fromisoformat(row[2]).date() == datetime.now().date()])
def cmd_list():
    list(map(print_message, aios_db.query("feed", "SELECT id, content, timestamp, source FROM messages ORDER BY timestamp DESC LIMIT 50")))
def print_view_message(row, time_fmt):
    time_str = datetime.fromisoformat(row[2]).strftime(time_fmt)
    date_str = row[2].split('T')[0]
    print({True: f"{time_str} {row[1]}", False: f"{date_str} {time_str} {row[1]}"}[datetime.fromisoformat(row[2]).date() == datetime.now().date()])
def make_print_view(time_fmt):
    def print_wrapper(row):
        print_view_message(row, time_fmt)
    return print_wrapper
def cmd_view():
    aios_db.write('settings', {})
    settings = aios_db.read('settings')
    time_fmt = {True: '%I:%M %p', False: '%H:%M'}[settings.get('time_format', '12h') == '12h']
    messages = aios_db.query("feed", "SELECT id, content, timestamp, source FROM messages ORDER BY timestamp DESC LIMIT 50")
    list(map(make_print_view(time_fmt), messages))
def cmd_clear():
    aios_db.execute("feed", "DELETE FROM messages WHERE timestamp < datetime('now', '-7 days')")
{"add": cmd_add, "list": cmd_list, "view": cmd_view, "clear": cmd_clear}.get(command, cmd_list)()