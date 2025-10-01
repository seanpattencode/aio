#!/usr/bin/env python3
import sys, subprocess
sys.path.append("/home/seanpatten/projects/AIOS/core")
import aios_db
cmd = (sys.argv + ["list"])[1]
job_id = (sys.argv + ["", None])[2]
jobs = aios_db.query("jobs", "SELECT id, name, status, output FROM jobs ORDER BY created DESC")
def print_job(j):
    output_text = {True: (j[3] or 'No output')[:50], False: 'No output'}[j[3] != None]
    print(f"{j[0]}: {j[1]} - {j[2]} - {output_text}...")
def print_running(j):
    print(f'<div class="job-item">{j[1]} <span class="status running">Running...</span></div>')
def print_review(j):
    output = {True: (j[3] or "")[:50] + "...", False: ""}[j[3] != None]
    print(f'<div class="job-item">{j[1]} <span class="output">{output}</span>')
    print(f'<form action="/job/accept" method="POST" style="display:inline"><input type="hidden" name="id" value="{j[0]}"><button class="action-btn">Accept</button></form>')
    print(f'<form action="/job/redo" method="POST" style="display:inline"><input type="hidden" name="id" value="{j[0]}"><button class="action-btn">Redo</button></form></div>')
def print_done(j):
    output = {True: (j[3] or "")[:50] + "...", False: ""}[j[3] != None]
    print(f'<div class="job-item">{j[1]} <span class="output">{output}</span></div>')
def is_running(j):
    return j[2] == "running"
def is_review(j):
    return j[2] == "review"
def is_done(j):
    return j[2] == "done"
def cmd_summary():
    running = list(filter(is_running, jobs))
    review = list(filter(is_review, jobs))
    done = list(filter(is_done, jobs))[:5]
    summary = []
    list(map(summary.extend, [[f"RUN {j[1]}" for j in running[:2]], [f"? {j[1]}" for j in review[:1]], [f"DONE {j[1]}" for j in done[:1]]]))
    list(map(print, summary[:4]))
def cmd_running():
    list(map(print_running, filter(is_running, jobs[:10])))
def cmd_review():
    list(map(print_review, filter(is_review, jobs[:10])))
def cmd_done():
    list(map(print_done, filter(is_done, jobs[:50])))
def cmd_run_wiki():
    aios_db.execute("jobs", "INSERT INTO jobs(name, status) VALUES ('wiki', 'running')")
    new_id = aios_db.query("jobs", "SELECT MAX(id) FROM jobs")[0][0]
    subprocess.Popen(["python3", "programs/wiki_fetcher/wiki_fetcher.py", str(new_id)])
def cmd_accept():
    {True: None, False: aios_db.execute("jobs", "UPDATE jobs SET status='done' WHERE id=?", (int(job_id),))}[job_id == None]
def cmd_redo():
    {True: None, False: (aios_db.execute("jobs", "UPDATE jobs SET status='running' WHERE id=?", (int(job_id),)), subprocess.Popen(["python3", "programs/wiki_fetcher/wiki_fetcher.py", str(job_id)]))}[job_id == None]
def cmd_list():
    list(map(print_job, jobs[:20]))
{"summary": cmd_summary, "running": cmd_running, "review": cmd_review, "done": cmd_done, "run_wiki": cmd_run_wiki, "accept": cmd_accept, "redo": cmd_redo, "list": cmd_list}.get(cmd, cmd_list)()