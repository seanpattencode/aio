#!/usr/bin/env python3
import subprocess, sys
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
subprocess.run(["pkill", "-9", "-f", "core/aios_api.py"], stderr=subprocess.DEVNULL)
subprocess.run(["pkill", "-9", "-f", "services/web/web.py"], stderr=subprocess.DEVNULL)
aios_db.write("aios_pids", {})
print("AIOS stopped")
