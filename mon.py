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

def create_worktree(project_path, session_name):
    """Create git worktree in project/aiosWorktrees/session_name"""
    worktrees_dir = os.path.join(project_path, "aiosWorktrees")
    os.makedirs(worktrees_dir, exist_ok=True)
    worktree_path = os.path.join(worktrees_dir, session_name)

    # Get current branch
    result = sp.run(['git', '-C', project_path, 'branch', '--show-current'],
                    capture_output=True, text=True)
    branch = result.stdout.strip() or 'main'

    # Create worktree with new branch (detached from current branch)
    result = sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', f"wt-{session_name}", worktree_path, branch],
                    capture_output=True, text=True)

    if result.returncode == 0:
        return worktree_path
    else:
        print(f"✗ Failed to create worktree: {result.stderr.strip()}")
        return None

if not arg:
    print(f"""mon.py - tmux session manager

Sessions:  h=htop  t=top  g=gemini  c=codex  l=claude
Prompts:   gp=gemini+prompt  cp=codex+prompt  lp=claude+prompt

Usage:
  ./mon.py <key>           Attach to session (create if needed)
  ./mon.py +<key>          Create NEW instance with timestamp
  ./mon.py ++<key>         Create NEW instance with git worktree
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
  ./mon.py +c 0            New codex instance in project 0
  ./mon.py ++c 0           New codex with worktree in project 0
  ./mon.py l 2             Launch claude in project 2 (Workcycle)
  ./mon.py c /tmp          Launch codex in /tmp

Git Worktrees:
  ++ prefix creates worktree in <project>/aiosWorktrees/<session>/
  Creates new branch: wt-<session>
  Example: ~/projects/aios/aiosWorktrees/codex-223045/""")
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
elif arg.startswith('++'):
    # Create with worktree
    key = arg[2:]
    if key in sessions and work_dir_arg and work_dir_arg.isdigit():
        idx = int(work_dir_arg)
        if 0 <= idx < len(PROJECTS):
            project_path = PROJECTS[idx]
            base_name, cmd = sessions[key]
            ts = datetime.now().strftime('%H%M%S')
            name = f"{base_name}-{ts}"

            # Create worktree
            if worktree_path := create_worktree(project_path, name):
                print(f"✓ Created worktree: {worktree_path}")
                sp.run(['tmux', 'new', '-d', '-s', name, '-c', worktree_path, cmd])
                os.execvp('tmux', ['tmux', 'switch-client' if "TMUX" in os.environ else 'attach', '-t', name])
        else:
            print(f"✗ Invalid project index: {work_dir_arg}")
    else:
        print("✗ Usage: ./mon.py ++<key> <project#>")
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
