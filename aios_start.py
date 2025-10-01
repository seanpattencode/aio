#!/usr/bin/env python3
import subprocess, sys
sys.path.append('/home/seanpatten/projects/AIOS')
command = (sys.argv + ["start"])[1]
subprocess.run(["python3", f"/home/seanpatten/projects/AIOS/core/aios_{command}.py"] + sys.argv[2:])
