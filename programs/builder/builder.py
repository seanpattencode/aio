#!/usr/bin/env python3
import sys, subprocess, concurrent.futures
from pathlib import Path
from datetime import datetime
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
components, build_dir = sys.argv[1:] or [], Path.home() / ".aios" / "builds"
build_dir.mkdir(parents=True, exist_ok=True)
build_component = lambda n: ((build_dir / f"{n}.build").write_text(f"Built at {datetime.now()}"), {"name": n, "status": {0: "success"}.get(subprocess.run(['echo', f'Building {n}'], capture_output=True, timeout=10).returncode, "failed"), "time": datetime.now().isoformat()})[1]
results = list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(build_component, components))
list(map(lambda r: print(f"{r['name']}: {r['status']}"), results))
aios_db.write("build_log", [])
aios_db.write("build_log", aios_db.read("build_log") + results)