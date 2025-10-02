#!/usr/bin/env python3
import sys
sys.path.extend(['/home/seanpatten/projects/AIOS', '/home/seanpatten/projects/AIOS/core'])
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, aios_db, subprocess, os, asyncio, websockets, pty, struct, fcntl, termios, signal
from urllib.parse import parse_qs, urlparse
from datetime import datetime
from pathlib import Path
from threading import Thread

TEMPLATE_DIR = Path(__file__).parent / 'templates'
WEB_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080

# Load templates
T = {}
template_files = {
    'index': 'index.html',
    'todo': 'todo.html',
    'jobs': 'jobs.html',
    'feed': 'feed.html',
    'autollm': 'autollm.html',
    'autollm_output': 'autollm_output.html',
    'terminal': 'terminal.html',
    'terminal_emulator': 'terminal-emulator.html',
    'terminal_xterm': 'terminal-xterm.html',
    'settings': 'settings.html',
    'workflow': 'workflow.html',
    'workflow_manager': 'workflow_manager.html'
}
for k, v in template_files.items():
    T[k] = (TEMPLATE_DIR / v).read_text()

class Handler(BaseHTTPRequestHandler):
    def _ctx(self):
        s = aios_db.read("settings") or {}
        c = {}
        c.update({
            'bg': {'light': '#fff'}.get(s.get('theme'), '#000'),
            'fg': {'light': '#000'}.get(s.get('theme'), '#fff'),
            'bg2': {'light': '#f0f0f0'}.get(s.get('theme'), '#1a1a1a')
        })
        return s, c

    def _get_todo_html(self, c):
        cmd = ["python3", "core/aios_runner.py", "python3", "programs/todo/todo.py", "list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        tasks = result.stdout.strip().split('\n') if result.stdout.strip() else []

        task_html = []
        for i, t in enumerate(tasks):
            done_class = "done" if "[x]" in t else ""
            task_id = t.split(".")[0] if "." in t else str(i+1)
            html = f'''<div class="task {done_class}">{t}
                <form style="display:inline" action="/todo/done" method="POST">
                    <input type="hidden" name="id" value="{task_id}">
                    <button>Done</button>
                </form>
            </div>'''
            task_html.append(html)

        tasks_content = "".join(task_html) or '<div style="color:#888">No tasks yet</div>'
        return T['todo'].format(**c, tasks=tasks_content)

    def _get_feed_html(self, s, c):
        messages = aios_db.query("feed", "SELECT content, timestamp FROM messages ORDER BY timestamp DESC LIMIT 100")

        if not messages:
            feed_content = "<div style='color:#888'>No messages yet</div>"
        else:
            seen_dates = []
            feed_items = []
            time_fmt = "12h" if s.get("time_format", "12h") == "12h" else "24h"

            for content, timestamp in messages:
                msg_date = datetime.fromisoformat(timestamp).date()

                # Add date header if new date
                if msg_date not in seen_dates:
                    seen_dates.append(msg_date)
                    date_html = f'<div style="color:#888;font-weight:bold;margin:15px 0 5px">{msg_date}</div>'
                    feed_items.append(date_html)

                # Format time
                dt = datetime.fromisoformat(timestamp)
                if time_fmt == "12h":
                    time_str = dt.strftime("%I:%M %p")
                else:
                    time_str = dt.strftime("%H:%M")

                # Add message
                msg_html = f'<div style="padding:8px;margin:2px 0">{time_str} - {content}</div>'
                feed_items.append(msg_html)

            feed_content = "".join(feed_items)

        return T['feed'].format(**c, feed_content=feed_content)

    def _get_settings_html(self, s, c):
        styles = {
            'theme_dark_style': 'style="font-weight:bold"' if s.get('theme', 'dark') == 'dark' else '',
            'theme_light_style': 'style="font-weight:bold"' if s.get('theme') == 'light' else '',
            'time_12h_style': 'style="font-weight:bold"' if s.get('time_format', '12h') == '12h' else '',
            'time_24h_style': 'style="font-weight:bold"' if s.get('time_format') == '24h' else ''
        }
        return T['settings'].format(**c, **styles)

    def _get_jobs_html(self, c):
        job_types = {'running_jobs': 'running', 'review_jobs': 'review', 'done_jobs': 'done'}
        job_data = {}

        for key, job_type in job_types.items():
            cmd = f"python3 services/jobs.py {job_type}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            content = result.stdout.strip()
            job_data[key] = content or f'<div style="color:#888;padding:10px">No {job_type} jobs</div>'

        return T['jobs'].format(**c, **job_data)

    def _get_autollm_html(self, c):
        def format_running(w):
            branch, path, job_id, status, task, model = w
            output_file = Path.home() / ".aios" / f"autollm_output_{job_id}.txt"
            if output_file.exists():
                output_text = output_file.read_text()[-200:]
            else:
                output_text = "Waiting for output..."

            return f'''<div class="worktree">
                <span class="status running">{branch}</span><br>
                {model}: {task[:30]}<br>
                <pre style="background:#000;padding:5px;margin:5px 0;max-height:100px;overflow-y:auto;font-size:10px">{output_text}</pre>
                <a href="/autollm/output?job_id={job_id}" style="padding:5px 10px;background:{c["fg"]};color:{c["bg"]};text-decoration:none;border-radius:3px">Full Output</a>
                <a href="/terminal?job_id={job_id}" style="padding:5px 10px;background:{c["fg"]};color:{c["bg"]};text-decoration:none;border-radius:3px;margin-left:5px">Terminal</a>
            </div>'''

        def format_review(w):
            branch, path, job_id, status, task, model, output = w
            output_preview = (output or "")[:50]
            return f'''<div class="worktree">
                <span class="status review">{branch}</span><br>
                {model}: {task[:30]}<br>
                Output: {output_preview}<br>
                <form action="/autollm/accept" method="POST" style="display:inline">
                    <input type="hidden" name="job_id" value="{job_id}">
                    <button>Accept</button>
                </form>
                <form action="/autollm/vscode" method="POST" style="display:inline">
                    <input type="hidden" name="path" value="{path}">
                    <button>VSCode</button>
                </form>
            </div>'''

        def format_done(w):
            branch = w[0]
            return f'<div class="worktree"><span class="status done">{branch}</span></div>'

        # Get worktrees
        all_worktrees = aios_db.query("autollm", "SELECT branch, path, job_id, status, task, model, output FROM worktrees")

        # Filter and format
        running = [w for w in all_worktrees if len(w) > 3 and w[3] == 'running']
        review = [w for w in all_worktrees if len(w) > 3 and w[3] == 'review']
        done = [w for w in all_worktrees if len(w) > 3 and w[3] == 'done']

        worktree_data = {
            'running_worktrees': "".join([format_running(w[:6]) for w in running]) or '<div style="color:#888">No running worktrees</div>',
            'review_worktrees': "".join([format_review(w) for w in review]) or '<div style="color:#888">No review worktrees</div>',
            'done_worktrees': "".join([format_done(w) for w in done]) or '<div style="color:#888">No done worktrees</div>'
        }

        return T['autollm'].format(**c, **worktree_data)

    def _get_autollm_output(self, c, job_id):
        output_file = Path.home() / ".aios" / f"autollm_output_{job_id}.txt"

        if output_file.exists():
            output_content = output_file.read_text()
        else:
            result = aios_db.query("autollm", "SELECT output FROM worktrees WHERE job_id=?", (job_id,))
            output_content = result[0][0] if result else "No output yet"

        return T['autollm_output'].format(**c, output_content=output_content)

    def _get_terminal(self, c, job_id):
        output_file = Path.home() / ".aios" / f"autollm_output_{job_id}.txt"
        terminal_content = output_file.read_text() if output_file.exists() else "Waiting for output..."
        return T['terminal'].format(**c, terminal_content=terminal_content, job_id=job_id)

    def _get_workflow_worktrees(self):
        cmd = ["git", "worktree", "list"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split('\n') if result.stdout.strip() else []

        worktrees = []
        for line in lines:
            if line and len(line.split()) >= 3:
                parts = line.split()
                worktrees.append({
                    "path": parts[0],
                    "branch": parts[2].strip('[]')
                })

        return json.dumps(worktrees)

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)
        s, c = self._ctx()

        # Route handlers
        routes = {
            '/': lambda: (T['index'].format(**c), 'text/html'),
            '/api/jobs': lambda: (
                json.dumps([
                    {"id": j[0], "name": j[1], "status": j[2], "output": j[3]}
                    for j in aios_db.query("jobs", "SELECT id, name, status, output FROM jobs ORDER BY created DESC")
                ]),
                'application/json'
            ),
            '/todo': lambda: (self._get_todo_html(c), 'text/html'),
            '/feed': lambda: (self._get_feed_html(s, c), 'text/html'),
            '/settings': lambda: (self._get_settings_html(s, c), 'text/html'),
            '/jobs': lambda: (self._get_jobs_html(c), 'text/html'),
            '/autollm': lambda: (self._get_autollm_html(c), 'text/html'),
            '/autollm/output': lambda: (
                self._get_autollm_output(c, q.get('job_id', [''])[0]),
                'text/html'
            ),
            '/terminal': lambda: (
                self._get_terminal(c, q.get('job_id', [''])[0]),
                'text/html'
            ),
            '/terminal-emulator': lambda: (
                T['terminal_emulator'].replace('ws://localhost:8766', f'ws://localhost:{WEB_PORT + 1000}'),
                'text/html'
            ),
            '/terminal-xterm': lambda: (
                T['terminal_xterm'].replace('ws://localhost:8766', f'ws://localhost:{WEB_PORT + 1000}'),
                'text/html'
            ),
            '/workflow': lambda: (T['workflow'].format(**c), 'text/html'),
            '/workflow-manager': lambda: (T['workflow_manager'].format(**c), 'text/html'),
            '/workflow/list_worktrees': lambda: (self._get_workflow_worktrees(), 'application/json'),
            '/api/workflow/nodes': lambda: (
                json.dumps(aios_db.read("workflow_nodes") or []),
                'application/json'
            )
        }

        # Get handler or default to index
        handler = routes.get(p.path, lambda: (T['index'].format(**c), 'text/html'))
        content, content_type = handler()

        # Send response
        self.send_response(200)
        self.send_header('Content-type', content_type)
        self.end_headers()
        self.wfile.write(content.encode())

    def do_POST(self):
        p = urlparse(self.path).path
        content_length = int(self.headers.get('Content-Length', 0))
        b = self.rfile.read(content_length) if content_length else b''

        # Handle workflow routes
        if p.startswith('/workflow/'):
            d = json.loads(b.decode() or '{}')

            if p == '/workflow/worktree_terminal':
                cmd = ["python3", "programs/workflow/workflow.py", "worktree_terminal",
                       d.get('repo', '/home/seanpatten/projects/AIOS'), d.get('branch', '')]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                output = json.loads(r.stdout) if r.stdout else {"error": "No output"}
                self.wfile.write(json.dumps(output).encode())
                return

            if p == '/workflow/remove_worktree':
                subprocess.run(["git", "worktree", "remove", d.get('path', '')], check=True, timeout=5)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"success":true}')
                return

            # Other workflow commands
            workflow_cmds = {
                '/workflow/add': f"python3 programs/workflow/workflow.py add {d.get('col', 0)} {d.get('text', '')}",
                '/workflow/expand': f"python3 programs/workflow/workflow.py expand {d.get('id', 0)} {d.get('text', '')}",
                '/workflow/branch': f"python3 programs/workflow/workflow.py branch {d.get('id', 0)}",
                '/workflow/exec': f"python3 programs/workflow/workflow.py exec {d.get('id', 0)}",
                '/workflow/push': f"python3 programs/workflow/workflow.py push {d.get('id', 0)}",
                '/workflow/term': f"python3 programs/workflow/workflow.py term {d.get('id', 0)}",
                '/workflow/comment': f"python3 programs/workflow/workflow.py comment {d.get('id', 0)} {d.get('text', '')}",
                '/workflow/save': f"python3 programs/workflow/workflow.py save {d.get('name', 'default')}",
                '/workflow/load': f"python3 programs/workflow/workflow.py load {d.get('name', 'default')}"
            }

            if p in workflow_cmds:
                subprocess.run(workflow_cmds[p], shell=True, timeout=5, capture_output=True)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            return

        # Handle shutdown
        if p == '/shutdown':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = b'<html><body><h1>Shutting down AIOS...</h1>'
            html += b'<script>setTimeout(function(){window.close();}, 2000);</script></body></html>'
            self.wfile.write(html)

            pids = aios_db.read("aios_pids") or {}
            for pid in pids.values():
                os.kill(pid, signal.SIGTERM)
            os._exit(0)

        # Handle restart
        if p == '/restart':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = b'<html><body><h1>Restarting AIOS...</h1>'
            html += b'<script>setTimeout(function(){location.href="/";}, 3000);</script></body></html>'
            self.wfile.write(html)

            def restart_aios():
                __import__('time').sleep(0.5)
                subprocess.Popen(["python3", "/home/seanpatten/projects/AIOS/core/aios_start.py"])
                __import__('time').sleep(1)
                os._exit(0)

            Thread(target=restart_aios, daemon=True).start()
            return

        # Handle worktree creation
        if p == '/worktree/create':
            d = parse_qs(b.decode()) or {}
            cmd = ["python3", "/home/seanpatten/projects/AIOS/programs/worktree/worktree_manager.py",
                   "create", d.get('repo', [''])[0], d.get('branch', [''])[0]]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            if r.returncode == 0:
                output = r.stdout
            else:
                output = f"Error: {r.stderr}"

            html = f'<html><body><h2>Worktree Created</h2><pre>{output}</pre>'
            html += '<br><a href="/">Back to Control Center</a></body></html>'
            self.wfile.write(html.encode())
            return

        # Handle other commands
        d = parse_qs(b.decode()) or {}

        commands = {
            '/job/run': "python3 services/jobs.py run_wiki",
            '/job/accept': f"python3 services/jobs.py accept {d.get('id', [''])[0]}",
            '/job/redo': f"python3 services/jobs.py redo {d.get('id', [''])[0]}",
            '/run': d.get('cmd', [''])[0],
            '/todo/add': f"python3 programs/todo/todo.py add {d.get('task', [''])[0]}",
            '/todo/done': f"python3 programs/todo/todo.py done {d.get('id', [''])[0]}",
            '/todo/clear': "python3 programs/todo/todo.py clear",
            '/settings/theme': f"python3 programs/settings/settings.py set theme {d.get('theme', ['dark'])[0]}",
            '/settings/time': f"python3 programs/settings/settings.py set time_format {d.get('format', ['12h'])[0]}",
            '/autollm/run': f"python3 programs/autollm/autollm.py run {d.get('repo', [''])[0]} "
                           f"{d.get('branches', ['1'])[0]} {d.get('model', ['claude-3-5-sonnet-20241022'])[0]} "
                           f"{d.get('task', [''])[0]}",
            '/autollm/accept': f"python3 programs/autollm/autollm.py accept {d.get('job_id', [''])[0]}",
            '/autollm/vscode': f"code {d.get('path', [''])[0]}",
            '/autollm/clean': "python3 programs/autollm/autollm.py clean"
        }

        if p in commands:
            subprocess.run(commands[p], shell=True, timeout=5, capture_output=True)

        # Redirect based on path
        if 'autollm' in p:
            redirect = '/autollm'
        elif 'settings' in p:
            redirect = '/settings'
        else:
            redirect = p.replace('/add', '').replace('/done', '').replace('/clear', '')

        self.send_response(303)
        self.send_header('Location', redirect)
        self.end_headers()

    def log_message(self, *args):
        pass

async def client_handler(ws):
    # Open PTY
    master, slave = pty.openpty()

    # Set terminal size
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))

    # Start bash process
    proc = await asyncio.create_subprocess_exec(
        'bash',
        stdin=slave,
        stdout=slave,
        stderr=slave,
        preexec_fn=os.setsid
    )

    os.close(slave)
    os.set_blocking(master, False)

    # Setup reading from PTY
    loop = asyncio.get_event_loop()

    def read_and_send():
        try:
            data = os.read(master, 65536)
            if data:
                asyncio.create_task(ws.send(data))
        except:
            pass

    loop.add_reader(master, read_and_send)

    try:
        async for msg in ws:
            if isinstance(msg, bytes):
                # Check if it's a resize command
                if msg[0:1] == b'{':
                    try:
                        d = json.loads(msg.decode())
                        if 'resize' in d:
                            rows = d['resize']['rows']
                            cols = d['resize']['cols']
                            fcntl.ioctl(master, termios.TIOCSWINSZ,
                                       struct.pack('HHHH', rows, cols, 0, 0))
                    except:
                        os.write(master, msg)
                else:
                    os.write(master, msg)
    finally:
        loop.remove_reader(master)
        proc.terminate()
        await proc.wait()
        os.close(master)

def serve_http(sock=None):
    s = HTTPServer(('', WEB_PORT), Handler, bind_and_activate=(sock is None))
    s.socket = sock if sock else s.socket
    s.serve_forever()

async def main():
    import socket

    # Get socket from parent if provided
    if len(sys.argv) > 1:
        sock = socket.fromfd(int(sys.argv[1]), socket.AF_INET, socket.SOCK_STREAM)
    else:
        sock = None

    # Start HTTP server in thread
    Thread(target=serve_http, args=(sock,), daemon=True).start()

    # Start WebSocket server
    ws_port = WEB_PORT + 1000
    try:
        async with websockets.serve(client_handler, 'localhost', ws_port):
            await asyncio.Future()
    except OSError:
        # Try alternate port if primary is busy
        async with websockets.serve(client_handler, 'localhost', WEB_PORT + 2000):
            await asyncio.Future()

asyncio.run(main())