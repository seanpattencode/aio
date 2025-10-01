#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
command = (sys.argv + ["set"])[1]
key = (sys.argv + ["set", "theme"])[2]
value = (sys.argv + ["set", "theme", ""])[3]
settings = aios_db.read("settings") or {}
[aios_db.write("settings", {**settings, key: value})] * (command == "set")
[print(settings.get(key, ""))] * (command == "get")
