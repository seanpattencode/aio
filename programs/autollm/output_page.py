#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db
job_id, output_file = (sys.argv + [""])[1], Path.home() / ".aios" / f"autollm_output_{(sys.argv + [''])[1]}.txt"
worktree = aios_db.query("autollm", "SELECT branch, task, model, status, output FROM worktrees WHERE job_id=?", (job_id,))
info = worktree[0] if worktree else ["unknown", "unknown", "unknown", "unknown", ""]
file_output = output_file.read_text() if output_file.exists() else (info[4] or "No output yet") if worktree else "No output yet"
list(map(print, [f"Branch: {info[0]}", f"Task: {info[1]}", f"Model: {info[2]}", f"Status: {info[3]}", f"Output:\n{file_output}"]))