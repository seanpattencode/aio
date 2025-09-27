#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db

job_id = (sys.argv + [""])[1]
worktree = aios_db.query("autollm", "SELECT path, output FROM worktrees WHERE job_id=?", (job_id,))
path = worktree[0][0]

output_file = Path(path) / ".autollm_output"
subprocess.run(["tail", "-f", str(output_file)], timeout=999999)