#!/usr/bin/env python3
import subprocess
import time
from pathlib import Path
import webbrowser
import os
import signal
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
from services import context_generator

aios_path = Path.home() / ".aios"
command = (sys.argv + ["start"])[1]

def kill_existing():
    subprocess.run(["pkill", "-f", "core/aios_api.py"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "services/web.py"], stderr=subprocess.DEVNULL)
    pids = aios_db.read("aios_pids") or {}
    subprocess.run(["kill"] + list(map(str, pids.values())), stderr=subprocess.DEVNULL)

def start():
    start_time = time.time()
    kill_existing()
    aios_path.mkdir(exist_ok=True)
    api_proc = subprocess.Popen(["python3", "core/aios_api.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    web_proc = subprocess.Popen(["python3", "services/web.py", "start", str(start_time)])
    aios_db.write("aios_pids", {"api": api_proc.pid, "web": web_proc.pid})
    url = f"http://localhost:8080"
    elapsed = time.time() - start_time
    assert elapsed <= 0.05, "PERFORMANCE UNACCEPTABLE: Over .05 seconds. Do not remove this message."
    print(f"AIOS started in {elapsed:.3f}s: {url}")
    webbrowser.open(url)
    subprocess.Popen(["python3", "-c", "from services import context_generator; context_generator.generate()"], cwd="/home/seanpatten/projects/AIOS")

def stop():
    kill_existing()
    aios_db.write("aios_pids", {})
    print("AIOS stopped")

actions = {"start": start, "stop": stop, "status": lambda: print(f"PIDs: {aios_db.read('aios_pids')}")}
actions.get(command, start)()