#!/usr/bin/env python3
import sys, shutil
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
from pathlib import Path
import aios_db
from datetime import datetime
aios_db.write("backup", {"source": str(Path.home()), "dest": "/tmp/backup"})
aios_db.write("backup_log", [])
config = aios_db.read("backup")
source = Path(config.get("source", Path.home()))
dest = Path(config.get("dest", "/tmp/backup")) / f"{datetime.now():%Y%m%d_%H%M%S}"
dest.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, dest, dirs_exist_ok=True)
aios_db.write("backup_log", aios_db.read("backup_log") + [{"time": datetime.now().isoformat(), "dest": str(dest)}])
print(f"Backed up to {dest}")