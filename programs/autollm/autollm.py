#!/usr/bin/env python3
import subprocess, sys
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db
command = (sys.argv + ["run"])[1]
create_and_launch = lambda repo, branch, model, task: (
    subprocess.run(["git", "worktree", "add", "-b", branch, str(Path(repo).parent / f"{Path(repo).name}-{branch}")], cwd=repo, capture_output=True, timeout=5),
    aios_db.execute("jobs", "INSERT INTO jobs(name, status) VALUES (?, 'running')", (branch,)),
    aios_db.execute("autollm", "INSERT INTO worktrees(repo, branch, path, job_id, model, task, status) VALUES (?, ?, ?, ?, ?, ?, 'running')",
                    (repo, branch, str(Path(repo).parent / f"{Path(repo).name}-{branch}"), aios_db.query("jobs", "SELECT MAX(id) FROM jobs")[0][0], model, task)),
    subprocess.Popen(["python3", "/home/seanpatten/projects/AIOS/core/aios_runner.py", "python3", "/home/seanpatten/projects/AIOS/programs/autollm/capture_output.py",
                     str(aios_db.query("jobs", "SELECT MAX(id) FROM jobs")[0][0]),
                     "claude-dangerous" if model == "claude-dangerous" else "claude" if model.startswith("claude") else "codex", model, task],
                    cwd=str(Path(repo).parent / f"{Path(repo).name}-{branch}"), env={**subprocess.os.environ, "AIOS_TIMEOUT": "999999"})
)
commands = {
    "run": lambda: list(map(lambda i: create_and_launch((sys.argv + ["", "/home/seanpatten/projects/testRepoPrivate"])[2], f"autollm-{Path((sys.argv + ['', '/home/seanpatten/projects/testRepoPrivate'])[2]).name}-{i}", (sys.argv + ["", "", "", "claude-3-5-sonnet-20241022"])[4], " ".join(sys.argv[5:]) or "Improve code"), range(int((sys.argv + ["", "", "1"])[3])))),
    "status": lambda: list(map(lambda w: print(f"{w[0]}: {w[1]}"), aios_db.query("autollm", "SELECT branch, status FROM worktrees"))),
    "clean": lambda: (list(map(lambda w: subprocess.run(["git", "worktree", "remove", w[2]], cwd=w[0], capture_output=True, timeout=5), aios_db.query("autollm", "SELECT repo, branch, path FROM worktrees WHERE status='done'"))), aios_db.execute("autollm", "DELETE FROM worktrees WHERE status='done'")),
    "output": lambda: print((lambda r: (r[0][0] or "") if r else "")(aios_db.query("autollm", "SELECT output FROM worktrees WHERE job_id=?", ((sys.argv + ["", ""])[2],)))),
    "accept": lambda: (aios_db.execute("autollm", "UPDATE worktrees SET status='done' WHERE job_id=?", ((sys.argv + ["", ""])[2],)), aios_db.execute("jobs", "UPDATE jobs SET status='done' WHERE id=?", ((sys.argv + ["", ""])[2],)))
}
commands.get(command, commands["run"])()