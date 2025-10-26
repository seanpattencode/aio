#!/usr/bin/env python3
import os, sys, subprocess as sp
from datetime import datetime

CLAUDE_PROMPT = "tell me a joke"
CODEX_PROMPT = "tell me a joke"
GEMINI_PROMPT = "tell me a joke"
WORK_DIR = os.getcwd()

PROJECTS = [
    os.path.expanduser("~/projects/aios"),
    os.path.expanduser("~/projects/waylandauto"),
    os.path.expanduser("~/AndroidStudioProjects/Workcycle"),
    os.path.expanduser("~/projects/testRepoPrivate")
]

sessions = {
    'h': ('htop', 'htop'),
    't': ('top', 'top'),
    'g': ('gemini', 'gemini --yolo'),
    'gp': ('gemini-p', f'gemini --yolo "{GEMINI_PROMPT}"'),
    'c': ('codex', 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox'),
    'cp': ('codex-p', f'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox "{CODEX_PROMPT}"'),
    'l': ('claude', 'claude --dangerously-skip-permissions'),
    'lp': ('claude-p', f'claude --dangerously-skip-permissions "{CLAUDE_PROMPT}"')
}

arg = sys.argv[1] if len(sys.argv) > 1 else None
work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None

# Resolve work_dir: digit -> PROJECTS[n], path -> path, None -> WORK_DIR
if work_dir_arg and work_dir_arg.isdigit():
    idx = int(work_dir_arg)
    work_dir = PROJECTS[idx] if 0 <= idx < len(PROJECTS) else WORK_DIR
else:
    work_dir = work_dir_arg if work_dir_arg else WORK_DIR

if not arg:
    print(f"""mon.py - tmux session manager

Sessions:  h=htop  t=top  g=gemini  c=codex  l=claude
Prompts:   gp=gemini+prompt  cp=codex+prompt  lp=claude+prompt

Usage:
  ./mon.py <key>           Attach to session (create if needed)
  ./mon.py +<key>          Create NEW instance with timestamp
  ./mon.py <key> <dir>     Start session in custom directory
  ./mon.py <key> <#>       Start session in saved project (#=0-{len(PROJECTS)-1})
  ./mon.py p               List saved projects
  ./mon.py ls              List all sessions
  ./mon.py x               Kill all sessions

Working Directory:
  Default: {WORK_DIR}

Saved Projects (edit at line 10):""")
    for i, proj in enumerate(PROJECTS):
        exists = "✓" if os.path.exists(proj) else "✗"
        print(f"  {i}. {exists} {proj}")
    print(f"""
Examples:
  ./mon.py c 0             Launch codex in project 0 (aios)
  ./mon.py l 2             Launch claude in project 2 (Workcycle)
  ./mon.py +c 1            New codex instance in project 1 (waylandauto)
  ./mon.py c /tmp          Launch codex in /tmp""")
elif arg == 'p':
    print("Saved Projects:")
    for i, proj in enumerate(PROJECTS):
        exists = "✓" if os.path.exists(proj) else "✗"
        print(f"  {i}. {exists} {proj}")
elif arg == 'ls':
    sp.run(['tmux', 'ls'])
elif arg == 'x':
    sp.run(['tmux', 'kill-server'])
    print("✓ All sessions killed")
elif arg.startswith('+'):
    key = arg[1:]
    if key in sessions:
        base_name, cmd = sessions[key]
        ts = datetime.now().strftime('%H%M%S')
        name = f"{base_name}-{ts}"
        sp.run(['tmux', 'new', '-d', '-s', name, '-c', work_dir, cmd])
        os.execvp('tmux', ['tmux', 'switch-client' if "TMUX" in os.environ else 'attach', '-t', name])
else:
    name, cmd = sessions.get(arg, (arg, None))
    sp.run(['tmux', 'new', '-d', '-s', name, '-c', work_dir, cmd or arg], capture_output=True)
    os.execvp('tmux', ['tmux', 'switch-client' if "TMUX" in os.environ else 'attach', '-t', name])
