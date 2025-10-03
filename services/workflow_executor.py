#!/usr/bin/env python3
import sys, subprocess
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db

def parse_workflow_md(md_path):
    steps, in_code, current = [], False, []
    for line in Path(md_path).read_text().split('\n'):
        if line.strip().startswith('```bash') or line.strip().startswith('```sh'):
            in_code, current = True, []
        elif in_code and line.strip().startswith('```'):
            steps.append('\n'.join(current))
            in_code = False
        elif in_code:
            current.append(line)
    return steps

def execute_workflow(worktree_id, workflow_path):
    steps = parse_workflow_md(workflow_path)
    workflows = aios_db.read("active_workflows") or {}
    workflows[worktree_id] = {"steps": steps, "current_step": 0, "results": [], "status": "ready", "workflow_path": workflow_path}
    aios_db.write("active_workflows", workflows)

    results = []
    for i, step in enumerate(steps):
        workflows[worktree_id].update({"current_step": i, "status": "executing"})
        aios_db.write("active_workflows", workflows)

        try:
            result = subprocess.run(step, shell=True, capture_output=True, text=True, timeout=300, cwd=Path.home() / ".aios")
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            output = "Timeout"
        except Exception as e:
            output = f"Error: {e}"

        results.append({"step": i, "command": step, "output": output[-500:]})
        workflows[worktree_id]["results"] = results
        aios_db.write("active_workflows", workflows)

    workflows[worktree_id]["status"] = "completed"
    aios_db.write("active_workflows", workflows)
    return {"status": "completed", "results": results}

if __name__ == "__main__":
    cmd = (sys.argv + ["execute"])[1]
    if cmd == "execute":
        wt_id = (sys.argv + ["", "default"])[2]
        wf_path = (sys.argv + ["", "", "workflow.md"])[3]
        result = execute_workflow(wt_id, wf_path)
        print(result)
    elif cmd == "parse":
        wf_path = (sys.argv + ["", "", "workflow.md"])[2]
        steps = parse_workflow_md(wf_path)
        for i, step in enumerate(steps):
            print(f"{i+1}. {step}")
