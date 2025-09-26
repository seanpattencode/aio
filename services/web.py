#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, aios_db, subprocess, os, socket
from urllib.parse import parse_qs, urlparse
from datetime import datetime

aios_db.execute("jobs", "CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, name TEXT, status TEXT, output TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
aios_db.execute("feed", "CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT, source TEXT, priority INTEGER DEFAULT 0)")

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
.dropdown{{display:none;position:absolute;background:{bg2};border:1px solid {fg};border-radius:5px;padding:10px;margin-top:5px}}
</style>
<script>
function toggleMenu() {{
    const menu = document.getElementById('job-menu');
    menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}}
function updateJobs() {{
    fetch('/api/jobs').then(r => r.json()).then(jobs => {{
        ['running', 'review', 'done'].forEach(status => {{
            const items = jobs.filter(j => j.status === status).slice(0, status === 'done' ? 50 : 10);
            document.getElementById(status).innerHTML = items.length ? items.map(j =>
                `<div class="job-item">${{j.name}} ${{status === 'running' ? '<span class="status running">Running...</span>' :
                status === 'review' ? `<span class="output">${{(j.output||'').slice(0,50)}}...</span><button class="action-btn" onclick="fetch('/api/job/accept',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:${{j.id}}}})}}),setTimeout(updateJobs,500)">Accept</button><button class="action-btn" onclick="fetch('/api/job/redo',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:${{j.id}}}})}}),setTimeout(updateJobs,500)">Redo</button>` :
                `<span class="output">${{(j.output||'').slice(0,50)}}...</span>`}}</div>`).join('')
            : '<div style="color:#888;padding:10px">No ' + (status === 'running' ? 'running' : status === 'review' ? 'jobs in review' : 'completed') + ' jobs</div>';
        }});
    }});
}}
updateJobs();
setInterval(updateJobs, 2000);
</script>
</head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Jobs</h1>
<button class="new-job-btn" onclick="toggleMenu()">Run New Job</button>
<div id="job-menu" class="dropdown">
  <button onclick="fetch('/api/job/run',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}}),toggleMenu(),setTimeout(updateJobs,500)" style="background:transparent;border:none;color:{fg};cursor:pointer;padding:8px;width:100%;text-align:left">Wikipedia Random Article</button>
  <div style="padding:8px;color:{fg}66;font-size:11px">More jobs coming soon...</div>
</div>

<div class="section">
<h2>RUNNING</h2>
<div id="running"><div style="color:#888;padding:10px">No running jobs</div></div>
</div>

<div class="section">
<h2>REVIEW</h2>
<div id="review"><div style="color:#888;padding:10px">No jobs in review</div></div>
</div>

<div class="section">
<h2>DONE</h2>
<div id="done"><div style="color:#888;padding:10px">No completed jobs</div></div>
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

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        s = aios_db.read("settings") or {}
        c = {'bg': '#fff' if s.get('theme') == 'light' else '#000', 'fg': '#000' if s.get('theme') == 'light' else '#fff', 'bg2': '#f0f0f0' if s.get('theme') == 'light' else '#1a1a1a'}

        if path == '/api/jobs':
            content = json.dumps([{"id": j[0], "name": j[1], "status": j[2], "output": j[3]} for j in aios_db.query("jobs", "SELECT id, name, status, output FROM jobs ORDER BY created DESC")])
            ctype = 'application/json'
        elif path == '/':
            tr = subprocess.run("python3 programs/todo/todo.py list", shell=True, capture_output=True, text=True)
            m = aios_db.query("feed", "SELECT content, timestamp FROM messages ORDER BY timestamp DESC LIMIT 4")
            j = aios_db.query("jobs", "SELECT name, status FROM jobs ORDER BY created DESC LIMIT 4")

            todo_items = tr.stdout.strip().split('\n')[:4] if tr.stdout.strip() else []
            feed_items = [f"{datetime.fromisoformat(x[1]).strftime('%I:%M %p' if s.get('time_format', '12h') == '12h' else '%H:%M')} - {x[0]}" for x in m] if m else []
            jobs_items = [f"{x[0]} - {x[1]}" for x in j] if j else []

            vp = "".join(f'''<div class="box" onclick="location.href='/{t.lower()}'">
<div class="box-title">{t}</div>
<div class="box-content">{"".join(f'<div class="box-item">{i}</div>' for i in items) if items else f'<div style="color:#888">No {t.lower()}</div>'}</div>
</div>''' for t, items in [('Todo', todo_items), ('Feed', feed_items), ('Jobs', jobs_items)])

            content = HTML_TEMPLATES['/'].format(**c, vp=vp)
            ctype = 'text/html'
        elif path == '/todo':
            result = subprocess.run("python3 programs/todo/todo.py list", shell=True, capture_output=True, text=True)
            tasks = result.stdout.strip().split('\n') if result.stdout.strip() else []
            tasks_html = "".join(f'<div class="task {"done" if "[x]" in t else ""}">{t} <form style="display:inline" action="/todo/done" method="POST"><input type="hidden" name="id" value="{t.split(".")[0] if "." in t else i+1}"><button>Done</button></form></div>' for i,t in enumerate(tasks))
            content = HTML_TEMPLATES['/todo'].format(**c, tasks=tasks_html if tasks else '<div style="color:#888">No tasks yet</div>')
            ctype = 'text/html'
        elif path == '/feed':
            messages = aios_db.query("feed", "SELECT content, timestamp FROM messages ORDER BY timestamp DESC LIMIT 100")
            time_format = s.get("time_format", "12h")
            feed_html = []
            current_date = None
            for m in messages:
                msg_date = datetime.fromisoformat(m[1]).date()
                if msg_date != current_date:
                    current_date = msg_date
                    feed_html.append(f'<div style="color:#888;font-weight:bold;margin:15px 0 5px">{current_date}</div>')
                feed_html.append(f'<div style="padding:8px;margin:2px 0">{datetime.fromisoformat(m[1]).strftime("%I:%M %p" if time_format == "12h" else "%H:%M")} - {m[0]}</div>')
            content = HTML_TEMPLATES['/feed'].format(**c, feed_content="".join(feed_html) if feed_html else "<div style='color:#888'>No messages yet</div>")
            ctype = 'text/html'
        elif path == '/settings':
            theme_dark_style = 'style="font-weight:bold"' if s.get('theme', 'dark') == 'dark' else ''
            theme_light_style = 'style="font-weight:bold"' if s.get('theme') == 'light' else ''
            time_12h_style = 'style="font-weight:bold"' if s.get('time_format', '12h') == '12h' else ''
            time_24h_style = 'style="font-weight:bold"' if s.get('time_format') == '24h' else ''
            content = HTML_TEMPLATES['/settings'].format(**c, theme_dark_style=theme_dark_style, theme_light_style=theme_light_style, time_12h_style=time_12h_style, time_24h_style=time_24h_style)
            ctype = 'text/html'
        elif path == '/jobs':
            content = HTML_TEMPLATES['/jobs'].format(**c)
            ctype = 'text/html'
        else:
            content = HTML_TEMPLATES.get(path, HTML_TEMPLATES['/']).format(**c, vp="", tasks="", feed_content="")
            ctype = 'text/html'

        self.send_response(200)
        self.send_header('Content-type', ctype)
        self.end_headers()
        self.wfile.write(content.encode())

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length > 0 else b''
        data = json.loads(body) if path.startswith('/api/') and body else parse_qs(body.decode()) if body else {}

        if path == '/api/job/run':
            aios_db.execute("jobs", "INSERT INTO jobs(name, status) VALUES ('wiki', 'running')")
            job_id = aios_db.query("jobs", "SELECT MAX(id) FROM jobs")[0][0]
            subprocess.Popen(["python3", "programs/wiki_fetcher/wiki_fetcher.py", str(job_id)])
        elif path == '/api/job/accept':
            aios_db.execute("jobs", "UPDATE jobs SET status='done' WHERE id=?", (data.get('id', 0),))
        elif path == '/api/job/redo':
            aios_db.execute("jobs", "UPDATE jobs SET status='running' WHERE id=?", (data.get('id', 0),))
            subprocess.Popen(["python3", "programs/wiki_fetcher/wiki_fetcher.py", str(data.get('id', 0))])
        elif path == '/run':
            subprocess.run(data.get('cmd', [''])[0], shell=True, capture_output=True, text=True, timeout=5)
        elif path == '/todo/add':
            subprocess.run(f"python3 programs/todo/todo.py add {data.get('task', [''])[0]}", shell=True)
        elif path == '/todo/done':
            subprocess.run(f"python3 programs/todo/todo.py done {data.get('id', [''])[0]}", shell=True)
        elif path == '/todo/clear':
            subprocess.run("python3 programs/todo/todo.py clear", shell=True)
        elif path == '/settings/theme':
            s = aios_db.read('settings') or {}
            s['theme'] = data.get('theme', ['dark'])[0]
            aios_db.write('settings', s)
        elif path == '/settings/time':
            s = aios_db.read('settings') or {}
            s['time_format'] = data.get('format', ['12h'])[0]
            aios_db.write('settings', s)

        self.send_response(303 if path not in ['/api/job/run', '/api/job/accept', '/api/job/redo'] else 200)
        self.send_header('Location', '/' if 'settings' in path else path.replace('/add', '').replace('/done', '').replace('/clear', '').replace('/api/', '/'))
        self.end_headers()

command = sys.argv[1] if len(sys.argv) > 1 else "start"

if command == 'start':
    port = 8080
    aios_db.write("web_server", {"port": port, "pid": os.getpid()})
    print(f"AIOS Control Center: http://localhost:{port}")
    HTTPServer(('', port), Handler).serve_forever()
elif command == 'stop':
    info = aios_db.read("web_server") or {}
    pid = info.get("pid")
    os.kill(pid, 15) if pid else print("No server running")
elif command == 'status':
    print(f"Server: {aios_db.read('web_server') or 'Not running'}")