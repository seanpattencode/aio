#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db
import subprocess

command = sys.argv[1] if len(sys.argv) > 1 else "summary"
job_id = sys.argv[2] if len(sys.argv) > 2 else None

jobs = aios_db.query("jobs", "SELECT id, name, status, output FROM jobs ORDER BY created DESC")

if command == "summary":
    running = [j for j in jobs if j[2] == "running"]
    review = [j for j in jobs if j[2] == "review"]
    done = [j for j in jobs if j[2] == "done"][:5]

    summary = []
    summary.extend([f"▶ {j[1]}" for j in running[:2]])
    summary.extend([f"? {j[1]}" for j in review[:1]])
    summary.extend([f"✓ {j[1]}" for j in done[:1]])

    for line in summary[:4]:
        print(line)

elif command == "running":
    running = [j for j in jobs if j[2] == "running"]
    for j in running[:10]:
        print(f'<div class="job-item">{j[1]} <span class="status running">Running...</span></div>')

elif command == "review":
    review = [j for j in jobs if j[2] == "review"]
    for j in review[:10]:
        output = (j[3] or "")[:50] + "..." if j[3] else ""
        print(f'<div class="job-item">{j[1]} <span class="output">{output}</span>')
        print(f'<form action="/job/accept" method="POST" style="display:inline"><input type="hidden" name="id" value="{j[0]}"><button class="action-btn">Accept</button></form>')
        print(f'<form action="/job/redo" method="POST" style="display:inline"><input type="hidden" name="id" value="{j[0]}"><button class="action-btn">Redo</button></form></div>')

elif command == "done":
    done = [j for j in jobs if j[2] == "done"]
    for j in done[:50]:
        output = (j[3] or "")[:50] + "..." if j[3] else ""
        print(f'<div class="job-item">{j[1]} <span class="output">{output}</span></div>')

elif command == "run_wiki":
    aios_db.execute("jobs", "INSERT INTO jobs(name, status) VALUES ('wiki', 'running')")
    job_id = aios_db.query("jobs", "SELECT MAX(id) FROM jobs")[0][0]
    subprocess.Popen(["python3", "programs/wiki_fetcher/wiki_fetcher.py", str(job_id)])

elif command == "accept" and job_id:
    aios_db.execute("jobs", "UPDATE jobs SET status='done' WHERE id=?", (int(job_id),))

elif command == "redo" and job_id:
    aios_db.execute("jobs", "UPDATE jobs SET status='running' WHERE id=?", (int(job_id),))
    subprocess.Popen(["python3", "programs/wiki_fetcher/wiki_fetcher.py", str(job_id)])