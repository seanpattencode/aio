#!/usr/bin/env python3
import schedule
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

services_db = Path.home() / ".aios" / "services.json"
schedule_db = Path.home() / ".aios" / "schedule.json"
services_db.parent.mkdir(exist_ok=True)
schedule_db.touch(exist_ok=True)

schedules = json.loads(schedule_db.read_text() or '{"daily": [], "hourly": []}')

[schedule.every().day.at("00:00").do(lambda s=s: subprocess.run(['python3', 'aios_cli.py', 'start', s])) for s in schedules.get('daily', [])]
[schedule.every().hour.do(lambda s=s: subprocess.run(['python3', 'aios_cli.py', 'start', s])) for s in schedules.get('hourly', [])]

[[schedule.run_pending(), time.sleep(1)] for _ in range(3600)]