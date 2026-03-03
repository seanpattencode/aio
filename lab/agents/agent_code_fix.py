#!/usr/bin/env python3
"""Finds biggest problem in aio and makes a small fix in a worktree"""
import sys,os,subprocess,datetime;sys.path.insert(0,__file__.rsplit('/',1)[0])
from agent_base import *

AIO_DIR=os.path.dirname(AIO)
WT_DIR=os.path.expanduser("~/projects/aiosWorktrees")

def make_fix():
    # Create worktree for this fix
    ts=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    wt=f"{WT_DIR}/autofix-{ts}"
    os.makedirs(WT_DIR,exist_ok=True)

    # Create worktree
    r=subprocess.run(['git','-C',AIO_DIR,'worktree','add','-b',f'autofix-{ts}',wt,'HEAD'],capture_output=True,text=True)
    if r.returncode!=0:
        return f"Failed to create worktree: {r.stderr}"

    prompt=f"""Read {wt}/aio.py fully.

Find the ONE biggest problem, bug, or missing feature that could be fixed in 10 lines or less.

Then use the Edit tool to make that fix in {wt}/aio.py.

Requirements:
- Change must be 10 lines or fewer
- Must be a clear improvement
- Must not break existing functionality

After making the edit, summarize what you changed and why in 2-3 sentences."""

    result=ask_claude(prompt,tools="Read,Glob,Grep,Edit",timeout=180)

    # Check if file was modified
    diff=subprocess.run(['git','-C',wt,'diff','--stat'],capture_output=True,text=True)

    return f"Worktree: {wt}\n\nClaude's response:\n{result}\n\nDiff:\n{diff.stdout or '(no changes)'}"

if __name__=="__main__":
    result=make_fix()
    print(f"Code Fix:\n{result}")
    if "--send" in sys.argv:
        send("Auto-fix attempted (hourly)",f"Attempted to fix biggest problem in aio.py\n\n{result}")
