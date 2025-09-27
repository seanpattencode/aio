#!/usr/bin/env python3
import sys
import subprocess
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db

worktrees = aios_db.query("autollm", "SELECT branch, path, job_id, status, model, task FROM worktrees")
list(map(lambda w: print(f"{w[0]}: {w[3]} | {w[4]} | {w[5][:30]}"), worktrees))