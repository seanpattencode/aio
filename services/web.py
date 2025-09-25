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

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            result = subprocess.run("python3 services/service.py list", shell=True, capture_output=True, text=True)
            services_text = result.stdout
            schedule = aios_db.read("schedule") or {}
            theme = self.headers.get('Cookie', '').split('theme=')[-1].split(';')[0] if 'theme=' in self.headers.get('Cookie', '') else 'dark'
            is_light = theme == 'light'
            bg = '#fff' if is_light else '#000'
            fg = '#000' if is_light else '#fff'
            bg2 = '#f0f0f0' if is_light else '#1a1a1a'
            html = f"""<html>
<head><title>AIOS Control Center</title>
<style>
body{{font-family:monospace;background:{bg};color:{fg};padding:20px}}
.container{{max-width:1200px;margin:0 auto}}
.service{{background:{bg2};padding:10px;margin:10px 0;border-radius:5px}}
button{{background:{fg};color:{bg};border:none;padding:5px 15px;cursor:pointer;margin:5px}}
input{{background:{bg2};color:{fg};border:1px solid {fg};padding:10px;width:80%;margin:10px 0}}
.running{{color:#0a0}} .stopped{{color:#a00}}
a{{color:{fg};text-decoration:underline}}
.theme-toggle{{position:fixed;top:20px;right:20px;cursor:pointer;padding:10px;background:{fg};color:{bg};border-radius:5px}}
</style></head>
<body>
<div class="theme-toggle" onclick="document.cookie='theme=' + (document.cookie.includes('theme=light') ? 'dark' : 'light') + ';path=/'; location.reload()">{'Light' if not is_light else 'Dark'}</div>
<div class="container">
<h1>AIOS Control Center</h1>
<h2>Quick Links</h2>
<a href="/todo">Todo Manager</a>
<h2>Services</h2>
<pre>{services_text}</pre>
<h2>Schedule</h2>
<div>Daily: {", ".join(f"{t}: {c}" for t,c in schedule.get("daily",{}).items())}</div>
<div>Hourly: {", ".join(f":{m:02d}: {c}" for m,c in schedule.get("hourly",{}).items())}</div>
<h2>Run Command</h2>
<form action="/run" method="POST">
<input name="cmd" placeholder="python3 programs/todo/todo.py list">
<button type="submit">Run</button>
</form>
<div id="output"></div>
</div></body></html>"""
            self.wfile.write(html.encode())
        elif path == '/todo':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            result = subprocess.run("python3 programs/todo/todo.py list", shell=True, capture_output=True, text=True)
            tasks = result.stdout.strip().split('\n') if result.stdout else []
            theme = self.headers.get('Cookie', '').split('theme=')[-1].split(';')[0] if 'theme=' in self.headers.get('Cookie', '') else 'dark'
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
.theme-toggle{{position:fixed;top:20px;right:20px;cursor:pointer;padding:10px;background:{fg};color:{bg};border-radius:5px}}
</style></head>
<body>
<div class="theme-toggle" onclick="document.cookie='theme=' + (document.cookie.includes('theme=light') ? 'dark' : 'light') + ';path=/'; location.reload()">{'Light' if not is_light else 'Dark'}</div>
<div style="margin-bottom:20px"><a href="/" style="padding:10px;background:{fg};color:{bg};border-radius:5px;text-decoration:none">Back</a></div>
<h1>Todo Manager</h1>
<form action="/todo/add" method="POST">
<input name="task" placeholder="New task...">
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