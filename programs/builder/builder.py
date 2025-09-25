#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
import subprocess
from pathlib import Path
import aios_db
from datetime import datetime
import concurrent.futures

components = sys.argv[1:] if len(sys.argv) > 1 else []
build_dir = Path.home() / ".aios" / "builds"
build_dir.mkdir(parents=True, exist_ok=True)

def build_component(name):
    result = subprocess.run(['echo', f'Building {name}'], capture_output=True, text=True)
    (build_dir / f"{name}.build").write_text(f"Built at {datetime.now()}")
    return {"name": name, "status": "success" if result.returncode == 0 else "failed", "time": datetime.now().isoformat()}

results = list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(build_component, components)) if components else []
[print(f"{r['name']}: {r['status']}") for r in results]
aios_db.write("build_log", aios_db.read("build_log") or [] + results)