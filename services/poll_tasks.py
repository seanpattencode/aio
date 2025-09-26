#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS/core')
import subprocess
import aios_db

subprocess.run(["inotifywait", "-m", "-e", "modify", f"{aios_db.db_path}/tasks.json"], stdout=subprocess.PIPE, text=True, check=False)