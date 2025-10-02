#!/usr/bin/env python3
import sys, shutil
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
from pathlib import Path
import aios_db
from datetime import datetime
[aios_db.write(*x) for x in [("backup", {"source": str(Path.home()), "dest": "/tmp/backup"}), ("backup_log", [])]]
c = aios_db.read("backup")
n = datetime.now()
dest = Path(c.get("dest", "/tmp/backup")) / f"{n:%Y%m%d_%H%M%S}"
[dest.parent.mkdir(parents=True, exist_ok=True), shutil.copytree(Path(c.get("source", str(Path.home()))), dest, dirs_exist_ok=True), aios_db.write("backup_log", aios_db.read("backup_log") + [{"time": n.isoformat(), "dest": str(dest)}]), print(f"Backed up to {dest}")]