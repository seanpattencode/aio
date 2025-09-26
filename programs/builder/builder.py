#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import subprocess
from pathlib import Path
import aios_db
from datetime import datetime
import concurrent.futures

components = sys.argv[1:] or []
build_dir = Path.home() / ".aios" / "builds"
build_dir.mkdir(parents=True, exist_ok=True)

def build_component(name):
    result = subprocess.run(['echo', f'Building {name}'], capture_output=True, text=True)
    (build_dir / f"{name}.build").write_text(f"Built at {datetime.now()}")
    status_map = {0: "success"}
    return {"name": name, "status": status_map.get(result.returncode, "failed"), "time": datetime.now().isoformat()}

def print_result(r):
    print(f"{r['name']}: {r['status']}")

results = list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(build_component, components))
list(map(print_result, results))
aios_db.write("build_log", [])
existing_log = aios_db.read("build_log")
aios_db.write("build_log", existing_log + results)