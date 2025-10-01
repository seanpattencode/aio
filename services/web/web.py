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

TEMPLATE_DIR = Path(__file__).parent / 'templates'
# Ram cache, no disk
TEMPLATE_INDEX = (TEMPLATE_DIR / 'index.html').read_text()
TEMPLATE_TODO = (TEMPLATE_DIR / 'todo.html').read_text()
TEMPLATE_JOBS = (TEMPLATE_DIR / 'jobs.html').read_text()
TEMPLATE_FEED = (TEMPLATE_DIR / 'feed.html').read_text()
TEMPLATE_AUTOLLM = (TEMPLATE_DIR / 'autollm.html').read_text()
TEMPLATE_AUTOLLM_OUTPUT = (TEMPLATE_DIR / 'autollm_output.html').read_text()
TEMPLATE_TERMINAL = (TEMPLATE_DIR / 'terminal.html').read_text()
TEMPLATE_SETTINGS = (TEMPLATE_DIR / 'settings.html').read_text()

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
        return (TEMPLATE_INDEX.format(**self.c, vp="", tasks="", feed_content="", running_jobs="", review_jobs="", done_jobs=""), 'text/html')

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
        return TEMPLATE_INDEX.format(**self.c, vp=vp), 'text/html'

    def handle_todo(self):
        result = subprocess.run(["python3", "core/aios_runner.py", "python3", "programs/todo/todo.py", "list"], capture_output=True, text=True)
        tasks = result.stdout.strip().split('\n') or []
        tasks_html = "".join(list(map(lambda it: f'<div class="task {"done" * ("[x]" in it[1])}">{it[1]} <form style="display:inline" action="/todo/done" method="POST"><input type="hidden" name="id" value="{it[1].split(".")[0] or str(it[0]+1)}"><button>Done</button></form></div>', enumerate(tasks))))
        return TEMPLATE_TODO.format(**self.c, tasks=tasks_html or '<div style="color:#888">No tasks yet</div>'), 'text/html'

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
        return TEMPLATE_FEED.format(**self.c, feed_content="".join(feed_html) or "<div style='color:#888'>No messages yet</div>"), 'text/html'

    def handle_settings(self):
        theme_dark_style = {'dark': 'style="font-weight:bold"'}.get(self.s.get('theme', 'dark'), '')
        theme_light_style = {'light': 'style="font-weight:bold"'}.get(self.s.get('theme'), '')
        time_12h_style = {'12h': 'style="font-weight:bold"'}.get(self.s.get('time_format', '12h'), '')
        time_24h_style = {'24h': 'style="font-weight:bold"'}.get(self.s.get('time_format'), '')
        return TEMPLATE_SETTINGS.format(**self.c, theme_dark_style=theme_dark_style, theme_light_style=theme_light_style, time_12h_style=time_12h_style, time_24h_style=time_24h_style), 'text/html'

    def handle_jobs(self):
        running = subprocess.run("python3 services/jobs.py running", shell=True, capture_output=True, text=True, timeout=5)
        review = subprocess.run("python3 services/jobs.py review", shell=True, capture_output=True, text=True, timeout=5)
        done = subprocess.run("python3 services/jobs.py done", shell=True, capture_output=True, text=True, timeout=5)
        running_html = running.stdout.strip() or '<div style="color:#888;padding:10px">No running jobs</div>'
        review_html = review.stdout.strip() or '<div style="color:#888;padding:10px">No jobs in review</div>'
        done_html = done.stdout.strip() or '<div style="color:#888;padding:10px">No completed jobs</div>'
        return TEMPLATE_JOBS.format(**self.c, running_jobs=running_html, review_jobs=review_html, done_jobs=done_html), 'text/html'

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
        return TEMPLATE_AUTOLLM.format(**self.c, running_worktrees=running_html, review_worktrees=review_html, done_worktrees=done_html), 'text/html'

    def handle_autollm_output(self):
        job_id = self.query.get('job_id', [''])[0]
        output_file = Path.home() / ".aios" / f"autollm_output_{job_id}.txt"
        db_output = aios_db.query("autollm", "SELECT output FROM worktrees WHERE job_id=?", (job_id,))
        output_content = output_file.read_text() * output_file.exists() or (db_output[0][0] or "No output yet") * bool(db_output) or "No output yet"
        return TEMPLATE_AUTOLLM_OUTPUT.format(**self.c, output_content=output_content), 'text/html'

    def handle_terminal(self):
        job_id = self.query.get('job_id', [''])[0]
        output_file = Path.home() / ".aios" / f"autollm_output_{job_id}.txt"
        terminal_content = (output_file.exists() and output_file.read_text()) or "Waiting for output..."
        return TEMPLATE_TERMINAL.format(**self.c, terminal_content=terminal_content, job_id=job_id), 'text/html'

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
