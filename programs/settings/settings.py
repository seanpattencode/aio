#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
command, key, value, settings = (sys.argv + ["set"])[1], (sys.argv + ["set", "theme"])[2], (sys.argv + ["set", "theme", ""])[3], aios_db.read("settings") or {}
{"set": lambda: aios_db.write("settings", {**settings, key: value}), "get": lambda: print(settings.get(key, ""))}[command]()
