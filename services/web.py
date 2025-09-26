#!/usr/bin/env python3

HTML_TEMPLATES = {
    '/': '''<!DOCTYPE html>
<html>
<head>
<title>AIOS Control Center</title>
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
.settings-btn{{position:fixed;top:20px;right:20px;padding:10px;background:{fg};color:{bg};border-radius:5px;cursor:pointer}}
</style>
</head>
<body>
<div class="settings-btn" onclick="location.href='/settings'">Settings</div>
<div class="container">
<h1>AIOS Control Center</h1>
<div class="viewport">{vp}</div>
<div class="run-box">
<h2 style="margin-top:0">Run Command</h2>
<form action="/run" method="POST">
<input name="cmd" placeholder="python3 programs/todo/todo.py list">
<button type="submit" class="run-button">Run</button>
</form>
</div>
</div>
</body>
</html>''',

    '/todo': '''<!DOCTYPE html>
<html>
<head>
<title>Todo</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.task{{background:{bg2};padding:10px;margin:5px 0;border-radius:5px}}
.done{{text-decoration:line-through;color:#666}}
button{{background:{fg};color:{bg};border:none;padding:5px 10px;cursor:pointer;margin:2px}}
input{{background:{bg2};color:{fg};border:1px solid {fg};padding:10px;width:50%;margin:10px 0}}
</style>
</head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Todo Manager</h1>
<form action="/todo/add" method="POST">
<input name="task" placeholder="New task... (use @ for deadline, e.g., Buy milk @ 14:30)">
<button type="submit">Add</button>
</form>
<div>{tasks}</div>
<form action="/todo/clear" method="POST"><button>Clear Completed</button></form>
</body>
</html>''',

    '/jobs': '''<!DOCTYPE html>
<html>
<head>
<title>Jobs</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px;max-width:1200px;margin:0 auto}}
h2{{margin:25px 0 10px;font-size:16px;color:{fg}99}}
.section{{margin-bottom:30px}}
.job-item{{background:{bg2};padding:15px;margin:8px 0;border-radius:5px;display:flex;justify-content:space-between;align-items:center}}
.status{{margin:0 10px}}
.status.running{{color:#fa0}}
.output{{color:{fg}88;margin:0 15px;font-size:12px;flex:1}}
.action-btn{{background:{fg};color:{bg};border:none;padding:8px 16px;cursor:pointer;border-radius:3px;font-size:12px;margin:0 5px}}
.action-btn:hover{{opacity:0.8}}
.new-job-btn{{background:{fg};color:{bg};border:none;padding:10px 20px;cursor:pointer;border-radius:5px;font-size:14px;margin:10px 0}}
</style>
</head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Jobs</h1>
<form action="/job/run" method="POST" style="display:inline">
<button type="submit" class="new-job-btn">Run Wikipedia Fetch</button>
</form>

<div class="section">
<h2>RUNNING</h2>
<div id="running">{running_jobs}</div>
</div>

<div class="section">
<h2>REVIEW</h2>
<div id="review">{review_jobs}</div>
</div>

<div class="section">
<h2>DONE</h2>
<div id="done">{done_jobs}</div>
</div>
</body>
</html>''',

    '/feed': '''<!DOCTYPE html>
<html>
<head>
<title>Feed</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.feed-box{{background:{bg2};border-radius:10px;padding:15px;height:400px;overflow-y:auto;margin:20px 0}}
button{{background:{fg};color:{bg};border:none;padding:5px 15px;cursor:pointer;margin:5px}}
</style>
</head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Feed</h1>
<div class="feed-box">{feed_content}</div>
</body>
</html>''',

    '/settings': '''<!DOCTYPE html>
<html>
<head>
<title>Settings</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.setting{{background:{bg2};padding:15px;margin:10px 0;border-radius:10px}}
button{{background:{fg};color:{bg};border:none;padding:10px 20px;cursor:pointer;margin:5px;border-radius:5px}}
</style>
</head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Settings</h1>
<div class="setting">
<h3>Theme</h3>
<form action="/settings/theme" method="POST">
<button type="submit" name="theme" value="dark" {theme_dark_style}>Dark Mode</button>
<button type="submit" name="theme" value="light" {theme_light_style}>Light Mode</button>
</form>
</div>
<div class="setting">
<h3>Time Format</h3>
<form action="/settings/time" method="POST">
<button type="submit" name="format" value="12h" {time_12h_style}>12-hour (AM/PM)</button>
<button type="submit" name="format" value="24h" {time_24h_style}>24-hour</button>
</form>
</div>
</body>
</html>'''
}

# All Python code at the end as requested
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, aios_db, subprocess, os, socket
from urllib.parse import parse_qs, urlparse
from datetime import datetime

aios_db.execute("jobs", "CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, name TEXT, status TEXT, output TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
aios_db.execute("feed", "CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT, source TEXT, priority INTEGER DEFAULT 0)")

def format_job(j):
    return {"id": j[0], "name": j[1], "status": j[2], "output": j[3]}

def handle_api_jobs():
    return (json.dumps(list(map(format_job, aios_db.query("jobs", "SELECT id, name, status, output FROM jobs ORDER BY created DESC")))), 'application/json')

def handle_default(c):
    return (HTML_TEMPLATES.get('/', HTML_TEMPLATES['/']).format(**c, vp="", tasks="", feed_content="", running_jobs="", review_jobs="", done_jobs=""), 'text/html')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        s = aios_db.read("settings") or {}
        c = {'bg': {'light': '#fff'}.get(s.get('theme'), '#000'), 'fg': {'light': '#000'}.get(s.get('theme'), '#fff'), 'bg2': {'light': '#f0f0f0'}.get(s.get('theme'), '#1a1a1a')}

        self.s = s
        self.c = c

        handlers = {
            '/api/jobs': handle_api_jobs,
            '/': self.handle_home,
            '/todo': self.handle_todo,
            '/feed': self.handle_feed,
            '/settings': self.handle_settings,
            '/jobs': self.handle_jobs
        }

        content, ctype = handlers.get(path, self.handle_default)()

        self.send_response(200)
        self.send_header('Content-type', ctype)
        self.end_headers()
        self.wfile.write(content.encode())

    def handle_default(self):
        return (HTML_TEMPLATES.get('/', HTML_TEMPLATES['/']).format(**self.c, vp="", tasks="", feed_content="", running_jobs="", review_jobs="", done_jobs=""), 'text/html')

    def handle_home(self):
        tr = subprocess.run("python3 programs/todo/todo.py list", shell=True, capture_output=True, text=True)
        m = aios_db.query("feed", "SELECT content, timestamp FROM messages ORDER BY timestamp DESC LIMIT 4")
        j = subprocess.run("python3 programs/job_status.py summary", shell=True, capture_output=True, text=True)

        todo_items = tr.stdout.strip().split('\n')[:4] or []
        def format_feed_item(x):
            return f"{datetime.fromisoformat(x[1]).strftime({'12h': '%I:%M %p'}.get(self.s.get('time_format', '12h'), '%H:%M'))} - {x[0]}"
        feed_items = list(map(format_feed_item, m)) or []
        jobs_summary = j.stdout.strip().split('\n')[:4] or ["No jobs"]

        def format_item(i):
            return f'<div class="box-item">{i}</div>'
        def format_box(entry):
            t, items = entry
            content = "".join(list(map(format_item, items))) or f'<div style="color:#888">No {t.lower()}</div>'
            return f'''<div class="box" onclick="location.href='/{t.lower()}'">
<div class="box-title">{t}</div>
<div class="box-content">{content}</div>
</div>'''
        vp = "".join(list(map(format_box, [('Todo', todo_items), ('Feed', feed_items), ('Jobs', jobs_summary)])))

        return HTML_TEMPLATES['/'].format(**self.c, vp=vp), 'text/html'

    def handle_todo(self):
        result = subprocess.run("python3 programs/todo/todo.py list", shell=True, capture_output=True, text=True)
        tasks = result.stdout.strip().split('\n') or []
        def format_task(indexed_task):
            i, t = indexed_task
            return f'<div class="task {"done" * ("[x]" in t)}">{t} <form style="display:inline" action="/todo/done" method="POST"><input type="hidden" name="id" value="{t.split(".")[0] or str(i+1)}"><button>Done</button></form></div>'
        tasks_html = "".join(list(map(format_task, enumerate(tasks))))
        return HTML_TEMPLATES['/todo'].format(**self.c, tasks=tasks_html or '<div style="color:#888">No tasks yet</div>'), 'text/html'

    def handle_feed(self):
        messages = aios_db.query("feed", "SELECT content, timestamp FROM messages ORDER BY timestamp DESC LIMIT 100")
        time_format = self.s.get("time_format", "12h")
        feed_html = []
        self._dates = []

        def process_message(m):
            date_header = {True: f'<div style="color:#888;font-weight:bold;margin:15px 0 5px">{datetime.fromisoformat(m[1]).date()}</div>', False: ''}.get(datetime.fromisoformat(m[1]).date() not in self._dates, '')
            feed_html.append(date_header + f'<div style="padding:8px;margin:2px 0">{datetime.fromisoformat(m[1]).strftime({"12h": "%I:%M %p"}.get(time_format, "%H:%M"))} - {m[0]}</div>')
            self._dates.append(datetime.fromisoformat(m[1]).date())

        list(map(process_message, messages))
        return HTML_TEMPLATES['/feed'].format(**self.c, feed_content="".join(feed_html) or "<div style='color:#888'>No messages yet</div>"), 'text/html'

    def handle_settings(self):
        theme_dark_style = {'dark': 'style="font-weight:bold"'}.get(self.s.get('theme', 'dark'), '')
        theme_light_style = {'light': 'style="font-weight:bold"'}.get(self.s.get('theme'), '')
        time_12h_style = {'12h': 'style="font-weight:bold"'}.get(self.s.get('time_format', '12h'), '')
        time_24h_style = {'24h': 'style="font-weight:bold"'}.get(self.s.get('time_format'), '')
        return HTML_TEMPLATES['/settings'].format(**self.c, theme_dark_style=theme_dark_style, theme_light_style=theme_light_style, time_12h_style=time_12h_style, time_24h_style=time_24h_style), 'text/html'

    def handle_jobs(self):
        running = subprocess.run("python3 programs/job_status.py running", shell=True, capture_output=True, text=True)
        review = subprocess.run("python3 programs/job_status.py review", shell=True, capture_output=True, text=True)
        done = subprocess.run("python3 programs/job_status.py done", shell=True, capture_output=True, text=True)

        running_html = running.stdout.strip() or '<div style="color:#888;padding:10px">No running jobs</div>'
        review_html = review.stdout.strip() or '<div style="color:#888;padding:10px">No jobs in review</div>'
        done_html = done.stdout.strip() or '<div style="color:#888;padding:10px">No completed jobs</div>'

        return HTML_TEMPLATES['/jobs'].format(**self.c, running_jobs=running_html, review_jobs=review_html, done_jobs=done_html), 'text/html'

    def post_job_run(self):
        return subprocess.run("python3 programs/job_status.py run_wiki", shell=True)

    def post_job_accept(self):
        return subprocess.run(f"python3 programs/job_status.py accept {self.data.get('id', [''])[0]}", shell=True)

    def post_job_redo(self):
        return subprocess.run(f"python3 programs/job_status.py redo {self.data.get('id', [''])[0]}", shell=True)

    def post_run_cmd(self):
        return subprocess.run(self.data.get('cmd', [''])[0], shell=True, capture_output=True, text=True, timeout=5)

    def post_todo_add(self):
        return subprocess.run(f"python3 programs/todo/todo.py add {self.data.get('task', [''])[0]}", shell=True)

    def post_todo_done(self):
        return subprocess.run(f"python3 programs/todo/todo.py done {self.data.get('id', [''])[0]}", shell=True)

    def post_todo_clear(self):
        return subprocess.run("python3 programs/todo/todo.py clear", shell=True)

    def post_settings_theme(self):
        return aios_db.write('settings', {**(aios_db.read('settings') or {}), 'theme': self.data.get('theme', ['dark'])[0]})

    def post_settings_time(self):
        return aios_db.write('settings', {**(aios_db.read('settings') or {}), 'time_format': self.data.get('format', ['12h'])[0]})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) or b''
        data = parse_qs(body.decode()) or {}
        self.data = data

        post_handlers = {
            '/job/run': self.post_job_run,
            '/job/accept': self.post_job_accept,
            '/job/redo': self.post_job_redo,
            '/run': self.post_run_cmd,
            '/todo/add': self.post_todo_add,
            '/todo/done': self.post_todo_done,
            '/todo/clear': self.post_todo_clear,
            '/settings/theme': self.post_settings_theme,
            '/settings/time': self.post_settings_time
        }

        handler = post_handlers.get(path, str)
        handler()

        self.send_response(303)
        self.send_header('Location', {'settings': '/'}.get('settings' * ('settings' in path), path.replace('/add', '').replace('/done', '').replace('/clear', '').replace('/run', '').replace('/accept', '').replace('/redo', '')))
        self.end_headers()

def cmd_start():
    aios_db.write("web_server", {"port": 8080, "pid": os.getpid()})
    print(f"AIOS Control Center: http://localhost:8080")
    HTTPServer(('', 8080), Handler).serve_forever()

def cmd_stop():
    info = aios_db.read("web_server") or {}
    pid = info.get("pid", 0)
    list(map(os.kill, [pid] * bool(pid), [15] * bool(pid)))
    list(map(print, ["No server running"] * (not bool(pid))))

def cmd_status():
    print(f"Server: {aios_db.read('web_server') or 'Not running'}")

command = (sys.argv + ["start"])[1]

cmd_handlers = {
    'start': cmd_start,
    'stop': cmd_stop,
    'status': cmd_status
}

cmd_handlers.get(command, cmd_handlers['start'])()