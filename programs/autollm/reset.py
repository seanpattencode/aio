#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db

aios_db.execute("autollm", "DROP TABLE IF EXISTS worktrees")
aios_db.execute("autollm", "CREATE TABLE IF NOT EXISTS worktrees(id INTEGER PRIMARY KEY, repo TEXT, branch TEXT, path TEXT, job_id INTEGER, model TEXT, task TEXT, status TEXT, output TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
print("Reset autollm database")