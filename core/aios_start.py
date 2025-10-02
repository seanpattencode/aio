#!/usr/bin/env python3
import subprocess, time, sys, socket, webbrowser
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
find_free_port = lambda: (lambda sk: (sk.bind(('', 0)), sk.getsockname()[1], sk.close())[1])(socket.socket())
aios_path, start_time = Path.home() / ".aios", time.time()
aios_path.mkdir(exist_ok=True)
web_port, api_port = find_free_port(), find_free_port()
aios_db.write("ports", {"web": web_port, "api": api_port}), aios_db.write("aios_pids", {})
web_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
[web_sock.setsockopt(socket.SOL_SOCKET, opt, 1) for opt in [socket.SO_REUSEADDR, socket.SO_REUSEPORT]]
web_sock.bind(('', web_port)), web_sock.listen(5)
api_proc = subprocess.Popen(["python3", "core/aios_api.py", str(api_port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
web_proc = subprocess.Popen(["python3", "services/web/web.py", str(web_sock.fileno()), str(web_port), str(api_port)], pass_fds=[web_sock.fileno()])
web_sock.close()
aios_db.write("aios_pids", {"api": api_proc.pid, "web": web_proc.pid})
print(f"AIOS started in {time.time()-start_time:.3f}s: http://localhost:{web_port}"), webbrowser.open(f"http://localhost:{web_port}")
subprocess.Popen(["python3", "-c", "from services import context_generator; context_generator.generate()"], cwd="/home/seanpatten/projects/AIOS")