#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db

command = (sys.argv + ["run"])[1]

aios_db.execute("autollm", "CREATE TABLE IF NOT EXISTS worktrees(id INTEGER PRIMARY KEY, repo TEXT, branch TEXT, path TEXT, job_id INTEGER, model TEXT, task TEXT, status TEXT, output TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
aios_db.execute("jobs", "CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, name TEXT, status TEXT, output TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

def run():
    repo = (sys.argv + ["", "/home/seanpatten/projects/testRepoPrivate"])[2]
    branches = int((sys.argv + ["", "1"])[3])
    model = (sys.argv + ["", "claude-3-5-sonnet-20241022"])[4]
    task = " ".join(sys.argv[5:]) or "Improve code"

    list(map(lambda i: create_and_launch(repo, f"autollm-{Path(repo).name}-{i}", model, task), range(branches)))

def create_and_launch(repo, branch, model, task):
    path = str(Path(repo).parent / f"{Path(repo).name}-{branch}")
    subprocess.run(["git", "worktree", "add", "-b", branch, path], cwd=repo, capture_output=True, timeout=5)
    aios_db.execute("jobs", "INSERT INTO jobs(name, status) VALUES (?, 'running')", (branch,))
    job_id = aios_db.query("jobs", "SELECT MAX(id) FROM jobs")[0][0]
    aios_db.execute("autollm", "INSERT INTO worktrees(repo, branch, path, job_id, model, task, status) VALUES (?, ?, ?, ?, ?, ?, 'running')",
                    (repo, branch, path, job_id, model, task))

    cmd_type = "claude" * (model.startswith("claude")) or "codex"
    subprocess.Popen(["python3", "/home/seanpatten/projects/AIOS/core/aios_runner.py", "python3", "/home/seanpatten/projects/AIOS/programs/autollm/llm.py", cmd_type, model, task], cwd=path, env={**subprocess.os.environ, "AIOS_TIMEOUT": "999999"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def status():
    worktrees = aios_db.query("autollm", "SELECT branch, status FROM worktrees")
    list(map(lambda w: print(f"{w[0]}: {w[1]}"), worktrees))

def clean():
    done = aios_db.query("autollm", "SELECT repo, branch, path FROM worktrees WHERE status='done'")
    list(map(lambda w: subprocess.run(["git", "worktree", "remove", w[2]], cwd=w[0], capture_output=True, timeout=5), done))
    aios_db.execute("autollm", "DELETE FROM worktrees WHERE status='done'")

def output():
    job_id = (sys.argv + ["", ""])[2]
    result = aios_db.query("autollm", "SELECT output FROM worktrees WHERE job_id=?", (job_id,))
    print((result[0][0] or "") * bool(result) or "")

def accept():
    job_id = (sys.argv + ["", ""])[2]
    aios_db.execute("autollm", "UPDATE worktrees SET status='done' WHERE job_id=?", (job_id,))
    aios_db.execute("jobs", "UPDATE jobs SET status='done' WHERE id=?", (job_id,))

{"run": run, "status": status, "clean": clean, "output": output, "accept": accept}.get(command, run)()