#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
print(f"PIDs: {aios_db.read('aios_pids')}")
