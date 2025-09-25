#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import aios_db
import socket
import os
import signal
import subprocess
from urllib.parse import parse_qs, urlparse
from datetime import datetime

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            settings = aios_db.read("settings") or {}
            viewports = settings.get('viewports', ['feed', 'processes', 'schedule', 'todo'])
            theme = settings.get('theme', 'dark')
            is_light = theme == 'light'
            bg = '#fff' if is_light else '#000'
            fg = '#000' if is_light else '#fff'
            bg2 = '#f0f0f0' if is_light else '#1a1a1a'
            time_format = settings.get("time_format", "12h")

            viewport_data = {}

            if 'todo' in viewports:
                todo_result = subprocess.run("python3 programs/todo/todo.py list", shell=True, capture_output=True, text=True)
                viewport_data['todo'] = {'title': 'Todo', 'items': todo_result.stdout.strip().split('\n')[:4] if todo_result.stdout else []}

            if 'feed' in viewports:
                messages = aios_db.query("feed", "SELECT content, timestamp FROM messages ORDER BY timestamp ASC LIMIT 4")
                viewport_data['feed'] = {'title': 'Feed', 'items': messages}

            if 'processes' in viewports:
                proc_result = subprocess.run("python3 services/processes.py list", shell=True, capture_output=True, text=True)
                viewport_data['processes'] = {'title': 'Processes', 'items': proc_result.stdout.strip().split('\n')[:4] if proc_result.stdout else []}

            if 'schedule' in viewports:
                schedule = aios_db.read("schedule") or {}
                schedule_items = []
                [[schedule_items.append(f"Daily {t}: {c}")] for t,c in sorted(schedule.get("daily",{}).items())]
                [[schedule_items.append(f"Hourly :{int(m):02d}: {c}")] for m,c in sorted(schedule.get("hourly",{}).items(), key=lambda x: int(x[0]))]
                viewport_data['schedule'] = {'title': 'Schedule', 'items': schedule_items[:4]}

            viewport_html = []
            for vp_name in viewports[:4]:
                if vp_name not in viewport_data:
                    continue
                data = viewport_data[vp_name]
                if vp_name == 'feed':
                    items_html = "".join(f'<div class="box-item">{datetime.fromisoformat(m[1]).strftime("%I:%M %p" if time_format == "12h" else "%H:%M")} - {m[0]}</div>' for m in data["items"]) if data["items"] else '<div style="color:#888">No messages</div>'
                else:
                    items_html = "".join(f'<div class="box-item">{item}</div>' for item in data["items"]) if data["items"] else f'<div style="color:#888">No {data["title"].lower()}</div>'

                viewport_html.append(f'''<div class="box" onclick="location.href='/{vp_name}'">
<div class="box-title">{data["title"]}</div>
<div class="box-content">{items_html}</div>
</div>''')

            html = f"""<html>
<head><title>AIOS Control Center</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.container{{max-width:1200px;margin:0 auto}}
.viewport{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}}
.box{{background:{bg2};border-radius:10px;padding:15px;cursor:pointer;position:relative}}
.box:hover{{opacity:0.9}}
.box-title{{font-weight:bold;margin-bottom:10px;font-size:18px}}
.box-content{{max-height:200px;overflow-y:auto}}
.box-item{{padding:5px 0;border-bottom:1px solid {fg}33}}
button{{background:{fg};color:{bg};border:none;padding:5px 15px;cursor:pointer;margin:5px;border-radius:5px}}
input{{background:{bg2};color:{fg};border:1px solid {fg};padding:12px;width:70%;margin:10px 0;border-radius:5px}}
.run-box{{background:{bg2};border-radius:10px;padding:20px;margin:20px 0}}
.run-button{{padding:12px 30px;font-size:16px}}
.running{{color:#0a0}} .stopped{{color:#a00}}
a{{color:{fg};text-decoration:underline}}
.menu-btn{{position:fixed;top:20px;cursor:pointer;padding:10px;background:{fg};color:{bg};border-radius:5px}}
.settings-btn{{right:20px}}
.views-btn{{right:120px}}
.dropdown{{display:none;position:fixed;top:60px;background:{bg2};border:1px solid {fg};border-radius:10px;padding:10px;min-width:150px;z-index:1000}}
.dropdown.views{{right:120px}}
.dropdown.settings{{right:20px}}
.dropdown-item{{padding:8px 12px;cursor:pointer;border-radius:5px}}
.dropdown-item:hover{{background:{bg}}}
.dropdown.show{{display:block}}
</style>
<script>
function toggleDropdown(type) {{
  const dropdown = document.getElementById(type + '-dropdown');
  const other = type === 'views' ? 'settings' : 'views';
  document.getElementById(other + '-dropdown').classList.remove('show');
  dropdown.classList.toggle('show');
}}
window.onclick = function(e) {{
  if (!e.target.matches('.menu-btn') && !e.target.closest('.dropdown')) {{
    document.querySelectorAll('.dropdown').forEach(d => d.classList.remove('show'));
  }}
}}
</script>
</head>
<body>
<div class="menu-btn views-btn" onclick="toggleDropdown('views')">Views</div>
<div class="dropdown views" id="views-dropdown">
<form action="/views/update" method="POST" id="viewsForm" style="margin:0">
{''.join(f'<label class="dropdown-item" style="display:block;padding:8px 12px;margin:0;cursor:pointer"><input type="checkbox" name="viewport" value="{vp}" {"checked" if vp in viewports else ""} onchange="document.getElementById(\'viewsForm\').submit()" style="margin:0 5px 0 0;accent-color:{fg};vertical-align:middle;width:14px;height:14px">{i+1}. {vp.title()}</label>' for i, vp in enumerate(['feed', 'processes', 'schedule', 'todo']))}
</form>
<div class="dropdown-item" onclick="location.href='/views'" style="font-size:12px;color:{fg}88;border-top:1px solid {fg}33;margin-top:5px;padding-top:10px">Advanced...</div>
</div>
<div class="menu-btn settings-btn" onclick="toggleDropdown('settings')">Settings</div>
<div class="dropdown settings" id="settings-dropdown">
<form action="/settings/theme" method="POST" style="margin:0"><button type="submit" name="theme" value="{'dark' if is_light else 'light'}" class="dropdown-item" style="display:flex;justify-content:space-between;width:100%;text-align:left;background:transparent;color:{fg};padding:8px 12px">Theme <span>{theme.title()}</span></button></form>
<form action="/settings/time" method="POST" style="margin:0"><button type="submit" name="format" value="{'24h' if time_format == '12h' else '12h'}" class="dropdown-item" style="display:flex;justify-content:space-between;width:100%;text-align:left;background:transparent;color:{fg};padding:8px 12px">Time <span>{time_format.upper()}</span></button></form>
<div class="dropdown-item" onclick="location.href='/settings'" style="font-size:12px;color:{fg}88">More...</div>
</div>
<div class="container">
<h1>AIOS Control Center</h1>
<div class="viewport">
{"".join(viewport_html)}
</div>
<div class="run-box">
<h2 style="margin-top:0">Run Command</h2>
<form action="/run" method="POST">
<input name="cmd" placeholder="python3 programs/todo/todo.py list">
<button type="submit" class="run-button">Run</button>
</form>
</div>
</div></body></html>"""
            self.wfile.write(html.encode())
        elif path == '/views':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            settings = aios_db.read("settings") or {}
            current_viewports = settings.get('viewports', ['feed', 'processes', 'schedule', 'todo'])
            all_viewports = ['feed', 'processes', 'schedule', 'todo']
            theme = settings.get('theme', 'dark')
            is_light = theme == 'light'
            bg = '#fff' if is_light else '#000'
            fg = '#000' if is_light else '#fff'
            bg2 = '#f0f0f0' if is_light else '#1a1a1a'
            html = f"""<html>
<head><title>View Configuration</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.viewport-item{{background:{bg2};padding:15px;margin:10px 0;border-radius:5px}}
button{{background:{fg};color:{bg};border:none;padding:10px 20px;cursor:pointer;margin:5px}}
input[type="checkbox"]{{margin-right:10px;accent-color:{fg}}}
</style></head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Configure Views</h1>
<form action="/views/update" method="POST">
<div class="viewport-item">
<h3>Select Viewports (max 4, order matters)</h3>
{"".join(f'<div><input type="checkbox" name="viewport" value="{vp}" {"checked" if vp in current_viewports else ""}>{i+1}. {vp.title()}</div>' for i, vp in enumerate(all_viewports))}
</div>
<button type="submit">Save</button>
</form>
</body></html>"""
            self.wfile.write(html.encode())
        elif path == '/processes':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            result = subprocess.run("python3 services/processes.py json", shell=True, capture_output=True, text=True)
            processes_data = json.loads(result.stdout) if result.stdout else {"scheduled": [], "ongoing": [], "core": []}
            settings = aios_db.read("settings") or {}
            theme = settings.get('theme', 'dark')
            is_light = theme == 'light'
            bg = '#fff' if is_light else '#000'
            fg = '#000' if is_light else '#fff'
            bg2 = '#f0f0f0' if is_light else '#1a1a1a'

            scheduled_html = "".join(f'<div class="process-item"><span class="time">{p["time"]}</span> {p["path"]} <button onclick="runProcess(\'{p["path"]}\')">Run</button></div>'
                                    for p in processes_data.get("scheduled", []))

            ongoing_html = "".join(f'<div class="process-item">{p["path"]} <span class="status active">●</span> <button onclick="restartProcess(\'{p["path"]}\')">Restart</button></div>'
                                 for p in processes_data.get("ongoing", []))

            core_html = "".join(f'<div class="process-item">{p["path"]} <button onclick="runProcess(\'{p["path"]}\')">Run</button></div>'
                              for p in processes_data.get("core", []))

            html = f"""<html>
<head><title>Processes</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px;max-width:1200px;margin:0 auto}}
h2{{margin:25px 0 10px;font-size:16px;color:{fg}99}}
.section{{margin-bottom:30px}}
.process-item{{background:{bg2};padding:12px;margin:4px 0;border-radius:5px;display:flex;justify-content:space-between;align-items:center}}
.time{{color:{fg}88;margin-right:15px;font-weight:bold}}
.status{{margin:0 10px}}
.status.active{{color:#0a0}}
button{{background:{fg};color:{bg};border:none;padding:4px 12px;cursor:pointer;border-radius:3px;font-size:12px}}
button:hover{{opacity:0.8}}
.toggle-section{{cursor:pointer;user-select:none;color:{fg}66;font-size:12px;margin-top:15px}}
.hidden{{display:none}}
</style>
<script>
function runProcess(path) {{
    fetch('/process/run', {{method: 'POST', body: new URLSearchParams({{'path': path}})}}
    ).then(() => location.reload());
}}
function restartProcess(path) {{
    fetch('/process/restart', {{method: 'POST', body: new URLSearchParams({{'path': path}})}}
    ).then(() => location.reload());
}}
function toggleCore() {{
    const core = document.getElementById('core-section');
    const toggle = document.getElementById('core-toggle');
    if (core.classList.contains('hidden')) {{
        core.classList.remove('hidden');
        toggle.textContent = '▼ Core Processes (hide)';
    }} else {{
        core.classList.add('hidden');
        toggle.textContent = '▶ Core Processes (show)';
    }}
}}
</script>
</head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Processes</h1>

<div class="section">
<h2>SCHEDULED</h2>
{scheduled_html if scheduled_html else '<div style="color:#888;padding:10px">No scheduled processes</div>'}
</div>

<div class="section">
<h2>ONGOING</h2>
{ongoing_html if ongoing_html else '<div style="color:#888;padding:10px">No ongoing processes</div>'}
</div>

<div class="section">
<div id="core-toggle" class="toggle-section" onclick="toggleCore()">▶ Core Processes (show)</div>
<div id="core-section" class="hidden">
<h2>CORE</h2>
{core_html}
</div>
</div>

</body></html>"""
            self.wfile.write(html.encode())
        elif path == '/schedule':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            schedule = aios_db.read("schedule") or {}
            settings = aios_db.read("settings") or {}
            theme = settings.get('theme', 'dark')
            is_light = theme == 'light'
            bg = '#fff' if is_light else '#000'
            fg = '#000' if is_light else '#fff'
            bg2 = '#f0f0f0' if is_light else '#1a1a1a'
            html = f"""<html>
<head><title>Schedule</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.schedule-item{{background:{bg2};padding:10px;margin:5px 0;border-radius:5px}}
</style></head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Schedule</h1>
<h2>Daily Tasks</h2>
<div>{"".join(f'<div class="schedule-item">{t}: {c}</div>' for t,c in sorted(schedule.get("daily",{}).items()))}</div>
<h2>Hourly Tasks</h2>
<div>{"".join(f'<div class="schedule-item">:{int(m):02d}: {c}</div>' for m,c in sorted(schedule.get("hourly",{}).items(), key=lambda x: int(x[0])))}</div>
</body></html>"""
            self.wfile.write(html.encode())
        elif path == '/feed':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            messages = aios_db.query("feed", "SELECT id, content, timestamp, source FROM messages ORDER BY timestamp ASC LIMIT 100")
            settings = aios_db.read("settings") or {}
            time_format = settings.get("time_format", "12h")
            theme = settings.get('theme', 'dark')
            is_light = theme == 'light'
            bg = '#fff' if is_light else '#000'
            fg = '#000' if is_light else '#fff'
            bg2 = '#f0f0f0' if is_light else '#1a1a1a'
            current_date = None
            feed_html = []
            [[feed_html.append(f'<div style="color:#888;font-weight:bold;margin:15px 0 5px">{datetime.fromisoformat(m[2]).date()}</div>') if (current_date := datetime.fromisoformat(m[2]).date()) != current_date else None,
              feed_html.append(f'<div style="padding:8px;margin:2px 0">{datetime.fromisoformat(m[2]).strftime("%I:%M %p" if time_format == "12h" else "%H:%M")} - {m[1]}</div>')]
             for m in messages]
            html = f"""<html>
<head><title>Feed</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.feed-box{{background:{bg2};border-radius:10px;padding:15px;height:400px;overflow-y:auto;margin:20px 0}}
button{{background:{fg};color:{bg};border:none;padding:5px 15px;cursor:pointer;margin:5px}}
</style></head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Feed</h1>
<div class="feed-box">{"".join(feed_html) if feed_html else "<div style='color:#888'>No messages yet</div>"}</div>
</body></html>"""
            self.wfile.write(html.encode())
        elif path == '/settings':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            settings = aios_db.read("settings") or {}
            time_format = settings.get("time_format", "12h")
            theme = settings.get('theme', 'dark')
            is_light = theme == 'light'
            bg = '#fff' if is_light else '#000'
            fg = '#000' if is_light else '#fff'
            bg2 = '#f0f0f0' if is_light else '#1a1a1a'
            html = f"""<html>
<head><title>Settings</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.setting{{background:{bg2};padding:15px;margin:10px 0;border-radius:10px}}
button{{background:{fg};color:{bg};border:none;padding:10px 20px;cursor:pointer;margin:5px;border-radius:5px}}
</style></head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Settings</h1>
<div class="setting">
<h3>Theme</h3>
<form action="/settings/theme" method="POST">
<button type="submit" name="theme" value="dark" {'style="font-weight:bold"' if theme == "dark" else ""}>Dark Mode</button>
<button type="submit" name="theme" value="light" {'style="font-weight:bold"' if theme == "light" else ""}>Light Mode</button>
</form>
</div>
<div class="setting">
<h3>Time Format</h3>
<form action="/settings/time" method="POST">
<button type="submit" name="format" value="12h" {'style="font-weight:bold"' if time_format == "12h" else ""}>12-hour (AM/PM)</button>
<button type="submit" name="format" value="24h" {'style="font-weight:bold"' if time_format == "24h" else ""}>24-hour</button>
</form>
</div>
</body></html>"""
            self.wfile.write(html.encode())
        elif path == '/todo':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            result = subprocess.run("python3 programs/todo/todo.py list", shell=True, capture_output=True, text=True)
            tasks = result.stdout.strip().split('\n') if result.stdout else []
            settings = aios_db.read("settings") or {}
            theme = settings.get('theme', 'dark')
            is_light = theme == 'light'
            bg = '#fff' if is_light else '#000'
            fg = '#000' if is_light else '#fff'
            bg2 = '#f0f0f0' if is_light else '#1a1a1a'
            html = f"""<html>
<head><title>Todo</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.task{{background:{bg2};padding:10px;margin:5px 0;border-radius:5px}}
.done{{text-decoration:line-through;color:#666}}
button{{background:{fg};color:{bg};border:none;padding:5px 10px;cursor:pointer;margin:2px}}
input{{background:{bg2};color:{fg};border:1px solid {fg};padding:10px;width:50%;margin:10px 0}}
</style></head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Todo Manager</h1>
<form action="/todo/add" method="POST">
<input name="task" placeholder="New task... (use @ for deadline, e.g., Buy milk @ 14:30)">
<button type="submit">Add</button>
</form>
<div>{"".join(f'<div class="task {"done" if "[x]" in t else ""}">{t} <form style="display:inline" action="/todo/done" method="POST"><input type="hidden" name="id" value="{t.split(".")[0] if "." in t else i+1}"><button>Done</button></form></div>' for i,t in enumerate(tasks))}</div>
<form action="/todo/clear" method="POST"><button>Clear Completed</button></form>
</body></html>"""
            self.wfile.write(html.encode())

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers['Content-Length'])
        data = parse_qs(self.rfile.read(length).decode())

        if path == '/run':
            cmd = data.get('cmd', [''])[0]
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            output = f"<pre>{result.stdout}\n{result.stderr}</pre>"
            self.wfile.write(f'<html><body><a href="/">Back</a><h2>Output:</h2>{output}</body></html>'.encode())
        elif path == '/todo/add':
            task = data.get('task', [''])[0]
            subprocess.run(f"python3 programs/todo/todo.py add {task}", shell=True)
            self.send_response(303)
            self.send_header('Location', '/todo')
            self.end_headers()
        elif path == '/todo/done':
            task_id = data.get('id', [''])[0]
            subprocess.run(f"python3 programs/todo/todo.py done {task_id}", shell=True)
            self.send_response(303)
            self.send_header('Location', '/todo')
            self.end_headers()
        elif path == '/todo/clear':
            subprocess.run("python3 programs/todo/todo.py clear", shell=True)
            self.send_response(303)
            self.send_header('Location', '/todo')
            self.end_headers()
        elif path == '/settings/time':
            format_val = data.get('format', ['12h'])[0]
            settings = aios_db.read('settings') or {}
            aios_db.write('settings', {**settings, 'time_format': format_val})
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        elif path == '/settings/theme':
            theme_val = data.get('theme', ['dark'])[0]
            settings = aios_db.read('settings') or {}
            aios_db.write('settings', {**settings, 'theme': theme_val})
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        elif path == '/views/update':
            selected = data.get('viewport', [])
            if not isinstance(selected, list):
                selected = [selected]
            settings = aios_db.read('settings') or {}
            aios_db.write('settings', {**settings, 'viewports': selected[:4]})
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        elif path == '/process/run':
            process_path = data.get('path', [''])[0]
            subprocess.Popen(['python3', process_path])
            self.send_response(303)
            self.send_header('Location', '/processes')
            self.end_headers()
        elif path == '/process/restart':
            process_path = data.get('path', [''])[0]
            subprocess.run(['pkill', '-f', process_path])
            subprocess.Popen(['python3', process_path])
            self.send_response(303)
            self.send_header('Location', '/processes')
            self.end_headers()

def find_free_port(start=8080):
    for port in range(start, start + 100):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        if result != 0:
            return port
    return start

def start_server():
    port = find_free_port()
    print(f"AIOS Control Center: http://localhost:{port}")
    aios_db.write("web_server", {"port": port, "pid": os.getpid()})
    HTTPServer(('', port), Handler).serve_forever()

def kill_server():
    info = aios_db.read("web_server")
    pid = info.get("pid") if info else None
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Killed server (PID: {pid})")
        except ProcessLookupError:
            print("Server not running")
    else:
        print("No server running")

command = sys.argv[1] if len(sys.argv) > 1 else "start"

actions = {
    "start": start_server,
    "stop": kill_server,
    "status": lambda: print(f"Server: {aios_db.read('web_server') or 'Not running'}"),
    "kill": kill_server
}

actions.get(command, start_server)()