#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from pathlib import Path
import subprocess

command = sys.argv[1] if len(sys.argv) > 1 else "check"
aios_path = Path.home() / ".aios"

actions = {
    "all": lambda: [aios_path.mkdir(exist_ok=True),
                    aios_db.write("config", {"setup": "complete", "version": "1.0"}),
                    subprocess.run(['pip', 'install', '-q', 'fastapi', 'uvicorn', 'schedule', 'anthropic']),
                    print("Setup complete")],
    "minimal": lambda: [aios_path.mkdir(exist_ok=True), aios_db.write("config", {"setup": "minimal"}), print("Minimal setup done")],
    "check": lambda: print("Setup: " + aios_db.read("config").get("setup", "not configured")),
    "reset": lambda: [subprocess.run(['rm', '-rf', str(aios_path)]), print("Reset complete")]
}

actions.get(command, actions["check"])()