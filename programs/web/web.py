#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import aios_db
import socket
import os
import signal

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        tasks = aios_db.read("tasks") or []
        html = f"""<html><body><h1>AIOS</h1><ul>{''.join(f'<li>{t}</li>' for t in tasks)}</ul>
        <form method="POST"><input name="task"><button>Add</button></form></body></html>"""
        self.wfile.write(html.encode())

    def do_POST(self):
        length = int(self.headers['Content-Length'])
        data = self.rfile.read(length).decode()
        task = data.split('=')[1] if '=' in data else ""
        tasks = aios_db.read("tasks") or []
        aios_db.write("tasks", tasks + [f"[ ] {task}"])
        self.send_response(303)
        self.send_header('Location', '/')
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
    print(f"Starting server at http://localhost:{port} (Ctrl+C to stop)")
    aios_db.write("web_server", {"port": port, "pid": os.getpid()})
    HTTPServer(('', port), Handler).serve_forever()

def kill_server():
    info = aios_db.read("web_server")
    pid = info.get("pid") if info else None
    if pid:
        os.kill(pid, signal.SIGTERM)
        print(f"Killed server (PID: {pid})")
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