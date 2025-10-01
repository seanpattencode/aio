#!/usr/bin/env python3
import subprocess, time, sys, socket, webbrowser
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
aios_path = Path.home() / ".aios"
start_time = time.time()
subprocess.run(["pkill", "-9", "-f", "core/aios_api.py"], stderr=subprocess.DEVNULL)
subprocess.run(["pkill", "-9", "-f", "services/web/web.py"], stderr=subprocess.DEVNULL)
aios_db.write("aios_pids", {})
aios_path.mkdir(exist_ok=True)
web_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
web_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
web_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
web_sock.bind(('', 8080))
web_sock.listen(5)
api_proc = subprocess.Popen(["python3", "core/aios_api.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
web_proc = subprocess.Popen(["python3", "services/web/web.py", str(web_sock.fileno())], pass_fds=[web_sock.fileno()])
web_sock.close()
aios_db.write("aios_pids", {"api": api_proc.pid, "web": web_proc.pid})
elapsed = time.time() - start_time
{True: None, False: print(f"AIOS started in {elapsed:.3f}s: http://localhost:8080")}[elapsed > 0.05]
webbrowser.open("http://localhost:8080")
subprocess.Popen(["python3", "-c", "from services import context_generator; context_generator.generate()"], cwd="/home/seanpatten/projects/AIOS")
