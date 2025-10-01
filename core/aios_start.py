#!/usr/bin/env python3
import subprocess, time, sys, webbrowser
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
aios_path = Path.home() / ".aios"
start_time = time.time()
subprocess.run(["pkill", "-f", "core/aios_api.py"], stderr=subprocess.DEVNULL)
subprocess.run(["pkill", "-f", "services/web/web.py"], stderr=subprocess.DEVNULL)
aios_db.write("aios_pids", {})
aios_path.mkdir(exist_ok=True)
api_proc = subprocess.Popen(["python3", "core/aios_api.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
web_proc = subprocess.Popen(["python3", "services/web/web.py", "start", str(start_time)])
aios_db.write("aios_pids", {"api": api_proc.pid, "web": web_proc.pid})
elapsed = time.time() - start_time
{True: None, False: print(f"AIOS started in {elapsed:.3f}s: http://localhost:8080")}[elapsed > 0.05]
webbrowser.open("http://localhost:8080")
subprocess.Popen(["python3", "-c", "from services import context_generator; context_generator.generate()"], cwd="/home/seanpatten/projects/AIOS")
