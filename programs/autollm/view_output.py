#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db
job_id, output_file, db_output = (sys.argv + [""])[1], Path.home() / ".aios" / f"autollm_output_{(sys.argv + [''])[1]}.txt", aios_db.query("autollm", "SELECT output FROM worktrees WHERE job_id=?", ((sys.argv + [""])[1],))
print(output_file.read_text() if output_file.exists() else (db_output[0][0] or "No output yet") if db_output else "No output yet")