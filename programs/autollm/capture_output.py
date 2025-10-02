#!/usr/bin/env python3
import subprocess, sys
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db
job_id, output_file, cmd_type, model, task = sys.argv[1], Path.home() / ".aios" / f"autollm_output_{sys.argv[1]}.txt", sys.argv[2], sys.argv[3], " ".join(sys.argv[4:])
result = subprocess.run({"claude": ["claude", task], "claude-dangerous": ["claude", "--dangerously-skip-permissions", task], "codex": ["codex", "-c", "model_reasoning_effort=high", "--model", model, "--dangerously-bypass-approvals-and-sandbox", task]}.get(cmd_type, ["echo", "Invalid command"]), capture_output=True, text=True, timeout=999999)
output = result.stdout + result.stderr
output_file.write_text(output)
list(map(lambda q: aios_db.execute(q[0], q[1], (output, job_id)), [("autollm", "UPDATE worktrees SET output=?, status='review' WHERE job_id=?"), ("jobs", "UPDATE jobs SET output=?, status='review' WHERE id=?")]))