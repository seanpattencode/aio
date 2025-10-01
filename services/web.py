#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, aios_db, subprocess, os, asyncio, websockets, pty, struct, fcntl, termios
from urllib.parse import parse_qs, urlparse
from datetime import datetime
from pathlib import Path
from threading import Thread

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

    '/autollm': '''<!DOCTYPE html>
<html>
<head>
<title>AutoLLM</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px;max-width:1200px;margin:0 auto}}
.worktree{{background:{bg2};padding:15px;margin:10px 0;border-radius:5px}}
.status{{font-weight:bold;color:#fa0}}
.running{{color:#0f0}}
.review{{color:#ff0}}
.done{{color:#888}}
button{{background:{fg};color:{bg};border:none;padding:8px 16px;cursor:pointer;border-radius:3px;margin:5px}}
input{{background:{bg2};color:{fg};border:1px solid {fg};padding:8px;margin:5px;border-radius:3px}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin:20px 0}}
</style>
</head>
<body>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>AutoLLM Worktree Manager</h1>
<form action="/autollm/run" method="POST">
<input name="repo" placeholder="Repository path" value="/home/seanpatten/projects/testRepoPrivate">
<input name="branches" placeholder="Number of branches" value="1" style="width:150px">
<select name="model" style="padding:8px;margin:5px;border-radius:3px;background:{bg2};color:{fg};border:1px solid {fg}">
<option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
<option value="claude-dangerous">Claude (--dangerously-skip-permissions)</option>
<option value="gpt-4">GPT-4</option>
<option value="gpt-5-codex">GPT-5 Codex</option>
</select>
<select name="preset" style="padding:8px;margin:5px;border-radius:3px;background:{bg2};color:{fg};border:1px solid {fg}" onchange="document.getElementsByName('task')[0].value=this.value">
<option value="">Select preset...</option>
<option value="Simplify and optimize this code">Simplify Code</option>
<option value="Add comprehensive tests">Add Tests</option>
<option value="Fix bugs and improve error handling">Fix Bugs</option>
<option value="Add type hints and documentation">Add Docs</option>
<option value="Refactor for better performance">Optimize Performance</option>
</select>
<input name="task" placeholder="Task description" style="width:400px">
<button type="submit">Launch Worktrees</button>
</form>
<div id="c">
<div class="grid">
<div>
<h2>Running</h2>
<div>{running_worktrees}</div>
</div>
<div>
<h2>Review</h2>
<div>{review_worktrees}</div>
</div>
<div>
<h2>Done</h2>
<div>{done_worktrees}</div>
</div>
</div>
</div>
<form action="/autollm/clean" method="POST">
<button>Clean Done Worktrees</button>
</form>
</body>
</html>''',

    '/autollm/output': '''<!DOCTYPE html>
<html>
<head>
<title>AutoLLM Output</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.output-box{{background:{bg2};padding:20px;border-radius:5px;margin:20px 0}}
pre{{white-space:pre-wrap;word-wrap:break-word}}
</style>
</head>
<body>
<div style="margin-bottom:20px"><a href="/autollm" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Job Output</h1>
<div class="output-box">
<pre>{output_content}</pre>
</div>
</body>
</html>''',

    '/terminal': '''<!DOCTYPE html>
<html>
<head>
<title>Terminal</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
#c{{background:#000;color:#0f0;padding:20px;border-radius:5px;height:500px;overflow-y:auto;white-space:pre-wrap}}
</style>
</head>
<body>
<div style="margin-bottom:20px"><a href="/autollm" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Terminal Output</h1>
<div id="c">{terminal_content}</div>
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
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        s = aios_db.read("settings") or {}
        c = {'bg': {'light': '#fff'}.get(s.get('theme'), '#000'), 'fg': {'light': '#000'}.get(s.get('theme'), '#fff'), 'bg2': {'light': '#f0f0f0'}.get(s.get('theme'), '#1a1a1a')}
        self.s = s
        self.c = c
        self.query = query
        handlers = {'/api/jobs': self.handle_api_jobs, '/': self.handle_home, '/todo': self.handle_todo, '/feed': self.handle_feed, '/settings': self.handle_settings, '/jobs': self.handle_jobs, '/autollm': self.handle_autollm, '/autollm/output': self.handle_autollm_output, '/terminal': self.handle_terminal}
        content, ctype = handlers.get(path, self.handle_default)()
        self.send_response(200)
        self.send_header('Content-type', ctype)
        self.end_headers()
        self.wfile.write(content.encode())

    def handle_default(self):
        return (HTML_TEMPLATES.get('/', HTML_TEMPLATES['/']).format(**self.c, vp="", tasks="", feed_content="", running_jobs="", review_jobs="", done_jobs=""), 'text/html')

    def handle_api_jobs(self):
        return (json.dumps(list(map(lambda j: {"id": j[0], "name": j[1], "status": j[2], "output": j[3]}, aios_db.query("jobs", "SELECT id, name, status, output FROM jobs ORDER BY created DESC")))), 'application/json')

    def handle_home(self):
        tr = subprocess.run(["python3", "core/aios_runner.py", "python3", "programs/todo/todo.py", "list"], capture_output=True, text=True)
        m = aios_db.query("feed", "SELECT content, timestamp FROM messages ORDER BY timestamp DESC LIMIT 4")
        j = subprocess.run(["python3", "core/aios_runner.py", "python3", "services/jobs.py", "summary"], capture_output=True, text=True)
        todo_items = tr.stdout.strip().split('\n')[:4] or []
        feed_items = list(map(lambda x: f"{datetime.fromisoformat(x[1]).strftime({'12h': '%I:%M %p'}.get(self.s.get('time_format', '12h'), '%H:%M'))} - {x[0]}", m)) or []
        jobs_summary = j.stdout.strip().split('\n')[:4] or ["No jobs"]
        boxes = [('Todo', todo_items), ('Feed', feed_items), ('Jobs', jobs_summary)]
        try:
            aios_db.query("autollm", "SELECT COUNT(*) FROM worktrees")
            boxes.append(('AutoLLM', ['Manage worktrees']))
        except: pass
        vp = "".join(list(map(lambda entry: f'''<div class="box" onclick="location.href='/{entry[0].lower()}'"><div class="box-title">{entry[0]}</div><div class="box-content">{"".join(list(map(lambda i: f'<div class="box-item">{i}</div>', entry[1]))) or f'<div style="color:#888">No {entry[0].lower()}</div>'}</div></div>''', boxes)))
        return HTML_TEMPLATES['/'].format(**self.c, vp=vp), 'text/html'

    def handle_todo(self):
        result = subprocess.run(["python3", "core/aios_runner.py", "python3", "programs/todo/todo.py", "list"], capture_output=True, text=True)
        tasks = result.stdout.strip().split('\n') or []
        tasks_html = "".join(list(map(lambda it: f'<div class="task {"done" * ("[x]" in it[1])}">{it[1]} <form style="display:inline" action="/todo/done" method="POST"><input type="hidden" name="id" value="{it[1].split(".")[0] or str(it[0]+1)}"><button>Done</button></form></div>', enumerate(tasks))))
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
        running = subprocess.run("python3 services/jobs.py running", shell=True, capture_output=True, text=True, timeout=5)
        review = subprocess.run("python3 services/jobs.py review", shell=True, capture_output=True, text=True, timeout=5)
        done = subprocess.run("python3 services/jobs.py done", shell=True, capture_output=True, text=True, timeout=5)
        running_html = running.stdout.strip() or '<div style="color:#888;padding:10px">No running jobs</div>'
        review_html = review.stdout.strip() or '<div style="color:#888;padding:10px">No jobs in review</div>'
        done_html = done.stdout.strip() or '<div style="color:#888;padding:10px">No completed jobs</div>'
        return HTML_TEMPLATES['/jobs'].format(**self.c, running_jobs=running_html, review_jobs=review_html, done_jobs=done_html), 'text/html'

    def handle_autollm(self):
        worktrees = aios_db.query("autollm", "SELECT branch, path, job_id, status, task, model, output FROM worktrees")
        running = []
        review = []
        done = []
        for w in worktrees:
            if w[3] == 'running': running.append((w[0], w[1], w[2], w[4], w[5]))
            elif w[3] == 'review': review.append((w[0], w[1], w[2], w[4], w[5], w[6]))
            elif w[3] == 'done': done.append((w[0], w[1]))
        running_html = "".join(list(map(lambda w: f'<div class="worktree"><span class="status running">{w[0]}</span><br>{w[4]}: {w[3][:30]}<br><pre style="background:#000;padding:5px;margin:5px 0;max-height:100px;overflow-y:auto;font-size:10px">{((Path.home() / ".aios" / f"autollm_output_{w[2]}.txt").read_text()[-200:] if (Path.home() / ".aios" / f"autollm_output_{w[2]}.txt").exists() else "Waiting for output...")}</pre><a href="/autollm/output?job_id={w[2]}" style="padding:5px 10px;background:{self.c["fg"]};color:{self.c["bg"]};text-decoration:none;border-radius:3px">Full Output</a><a href="/terminal?job_id={w[2]}" style="padding:5px 10px;background:{self.c["fg"]};color:{self.c["bg"]};text-decoration:none;border-radius:3px;margin-left:5px">Terminal</a></div>', running))) or '<div style="color:#888">No running worktrees</div>'
        review_html = "".join(list(map(lambda w: f'<div class="worktree"><span class="status review">{w[0]}</span><br>{w[4]}: {w[3][:30]}<br>Output: {(w[5] or "")[:50]}<br><form action="/autollm/accept" method="POST" style="display:inline"><input type="hidden" name="job_id" value="{w[2]}"><button>Accept</button></form><form action="/autollm/vscode" method="POST" style="display:inline"><input type="hidden" name="path" value="{w[1]}"><button>VSCode</button></form></div>', review))) or '<div style="color:#888">No worktrees in review</div>'
        done_html = "".join(list(map(lambda w: f'<div class="worktree"><span class="status done">{w[0]}</span></div>', done))) or '<div style="color:#888">No completed worktrees</div>'
        return HTML_TEMPLATES['/autollm'].format(**self.c, running_worktrees=running_html, review_worktrees=review_html, done_worktrees=done_html), 'text/html'

    def handle_autollm_output(self):
        job_id = self.query.get('job_id', [''])[0]
        output_file = Path.home() / ".aios" / f"autollm_output_{job_id}.txt"
        db_output = aios_db.query("autollm", "SELECT output FROM worktrees WHERE job_id=?", (job_id,))
        output_content = output_file.read_text() * output_file.exists() or (db_output[0][0] or "No output yet") * bool(db_output) or "No output yet"
        return HTML_TEMPLATES['/autollm/output'].format(**self.c, output_content=output_content), 'text/html'

    def handle_terminal(self):
        job_id = self.query.get('job_id', [''])[0]
        output_file = Path.home() / ".aios" / f"autollm_output_{job_id}.txt"
        terminal_content = (output_file.exists() and output_file.read_text()) or "Waiting for output..."
        return HTML_TEMPLATES['/terminal'].format(**self.c, terminal_content=terminal_content, job_id=job_id), 'text/html'

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) or b''
        data = parse_qs(body.decode()) or {}
        self.data = data
        post_handlers = {'/job/run': lambda: subprocess.run("python3 services/jobs.py run_wiki", shell=True, timeout=5), '/job/accept': lambda: subprocess.run(f"python3 services/jobs.py accept {self.data.get('id', [''])[0]}", shell=True, timeout=5), '/job/redo': lambda: subprocess.run(f"python3 services/jobs.py redo {self.data.get('id', [''])[0]}", shell=True, timeout=5), '/run': lambda: subprocess.run(self.data.get('cmd', [''])[0], shell=True, capture_output=True, text=True, timeout=5), '/todo/add': lambda: subprocess.run(f"python3 programs/todo/todo.py add {self.data.get('task', [''])[0]}", shell=True, timeout=5), '/todo/done': lambda: subprocess.run(f"python3 programs/todo/todo.py done {self.data.get('id', [''])[0]}", shell=True, timeout=5), '/todo/clear': lambda: subprocess.run("python3 programs/todo/todo.py clear", shell=True, timeout=5), '/settings/theme': lambda: aios_db.write('settings', {**(aios_db.read('settings') or {}), 'theme': self.data.get('theme', ['dark'])[0]}), '/settings/time': lambda: aios_db.write('settings', {**(aios_db.read('settings') or {}), 'time_format': self.data.get('format', ['12h'])[0]}), '/autollm/run': lambda: subprocess.run(["python3", "programs/autollm/autollm.py", "run", self.data.get('repo', [''])[0], self.data.get('branches', ['1'])[0], self.data.get('model', ['claude-3-5-sonnet-20241022'])[0], self.data.get('task', [''])[0]], timeout=5), '/autollm/accept': lambda: (aios_db.execute("autollm", "UPDATE worktrees SET status='done' WHERE job_id=?", (int(self.data.get('job_id', [''])[0]),)), aios_db.execute("jobs", "UPDATE jobs SET status='done' WHERE id=?", (int(self.data.get('job_id', [''])[0]),))), '/autollm/vscode': lambda: subprocess.run(["code", self.data.get('path', [''])[0]]), '/autollm/clean': lambda: subprocess.run(["python3", "programs/autollm/autollm.py", "clean"], timeout=5)}
        handler = post_handlers.get(path, str)
        handler()
        self.send_response(303)
        self.send_header('Location', '/autollm' * ('autollm' in path) or '/settings' * ('settings' in path) or path.replace('/add', '').replace('/done', '').replace('/clear', ''))
        self.end_headers()

    def log_message(self, *args): pass

async def client_handler(ws):
    master, slave = pty.openpty()
    winsize = struct.pack('HHHH', 24, 80, 0, 0)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
    proc = await asyncio.create_subprocess_exec('bash', stdin=slave, stdout=slave, stderr=slave, preexec_fn=os.setsid)
    os.close(slave)
    os.set_blocking(master, False)
    loop = asyncio.get_event_loop()
    def read_output():
        try:
            data = os.read(master, 65536)
            if data: asyncio.create_task(ws.send(data))
        except (OSError, BlockingIOError): pass
    loop.add_reader(master, read_output)
    try:
        async for msg in ws:
            if isinstance(msg, bytes):
                try:
                    data = json.loads(msg.decode('utf-8'))
                    if 'resize' in data:
                        size = data['resize']
                        winsize = struct.pack('HHHH', size['rows'], size['cols'], 0, 0)
                        fcntl.ioctl(master, termios.TIOCSWINSZ, winsize)
                        if 'term' in data: os.environ['TERM'] = data['term']
                except: os.write(master, msg)
    finally:
        loop.remove_reader(master)
        proc.terminate()
        await proc.wait()
        os.close(master)

async def main():
    Thread(target=lambda: HTTPServer(('', 8080), Handler).serve_forever(), daemon=True).start()
    async with websockets.serve(client_handler, 'localhost', 8766):
        await asyncio.Future()

if __name__ == '__main__': asyncio.run(main())
