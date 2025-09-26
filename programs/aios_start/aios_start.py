#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
import subprocess
import time
import aios_db
from pathlib import Path
import webbrowser
import os
import signal

aios_path = Path.home() / ".aios"
command = sys.argv[1] if len(sys.argv) > 1 else "start"

def kill_existing():
    subprocess.run(["pkill", "-f", "aios_api.py"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "programs/web/web.py"], stderr=subprocess.DEVNULL)
    pids = aios_db.read("aios_pids") or {}
    for pid in pids.values():
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

def start():
    start_time = time.time()
    kill_existing()
    aios_path.mkdir(exist_ok=True)
    api_proc = subprocess.Popen(["python3", "aios_api.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    web_proc = subprocess.Popen(["python3", "programs/web/web.py", "start"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    aios_db.write("aios_pids", {"api": api_proc.pid, "web": web_proc.pid})
    time.sleep(0.1)
    info = aios_db.read("web_server") or {}
    url = f"http://localhost:{info.get('port', 8080)}"
    elapsed = time.time() - start_time
    print(f"AIOS started in {elapsed:.3f}s: {url}")
    webbrowser.open(url)

def stop():
    kill_existing()
    aios_db.write("aios_pids", {})
    print("AIOS stopped")

actions = {
    "start": start,
    "stop": stop,
    "status": lambda: print(f"PIDs: {aios_db.read('aios_pids')}")
}

actions.get(command, start)()