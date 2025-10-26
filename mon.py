#!/usr/bin/env python3
import os, sys, subprocess as sp
from datetime import datetime

CLAUDE_PROMPT = "tell me a joke"
CODEX_PROMPT = "tell me a joke"
GEMINI_PROMPT = "tell me a joke"
WORK_DIR = os.getcwd()
WORKTREES_DIR = os.path.expanduser("~/projects/aiosWorktrees")

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

def detect_terminal():
    """Detect available terminal emulator"""
    for term in ['gnome-terminal', 'alacritty']:
        try:
            sp.run(['which', term], capture_output=True, check=True)
            return term
        except:
            pass
    return None

def launch_in_new_window(session_name, terminal=None):
    """Launch tmux session in new terminal window"""
    if not terminal:
        terminal = detect_terminal()

    if not terminal:
        print("✗ No supported terminal found (gnome-terminal, alacritty)")
        return False

    if terminal == 'gnome-terminal':
        cmd = ['gnome-terminal', '--', 'tmux', 'attach', '-t', session_name]
    elif terminal == 'alacritty':
        cmd = ['alacritty', '-e', 'tmux', 'attach', '-t', session_name]

    try:
        sp.Popen(cmd)
        print(f"✓ Launched {terminal} for session: {session_name}")
        return True
    except Exception as e:
        print(f"✗ Failed to launch terminal: {e}")
        return False

def launch_terminal_in_dir(directory, terminal=None):
    """Launch new terminal window in specific directory"""
    if not terminal:
        terminal = detect_terminal()

    if not terminal:
        print("✗ No supported terminal found (gnome-terminal, alacritty)")
        return False

    # Expand and resolve path
    directory = os.path.expanduser(directory)
    directory = os.path.abspath(directory)

    if not os.path.exists(directory):
        print(f"✗ Directory does not exist: {directory}")
        return False

    if terminal == 'gnome-terminal':
        cmd = ['gnome-terminal', f'--working-directory={directory}']
    elif terminal == 'alacritty':
        cmd = ['alacritty', '--working-directory', directory]

    try:
        sp.Popen(cmd)
        print(f"✓ Launched {terminal} in: {directory}")
        return True
    except Exception as e:
        print(f"✗ Failed to launch terminal: {e}")
        return False

# Parse args
arg = sys.argv[1] if len(sys.argv) > 1 else None
work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None
new_window = '--new-window' in sys.argv or '-w' in sys.argv

# Clean args
if new_window:
    sys.argv = [a for a in sys.argv if a not in ['--new-window', '-w']]
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None

# Check if arg is actually a directory/number (not a session key)
is_directory_only = new_window and arg and not arg.startswith('+') and arg not in sessions

# If directory-only mode, treat arg as work_dir_arg
if is_directory_only:
    work_dir_arg = arg
    arg = None

# Resolve work_dir: digit -> PROJECTS[n], path -> path, None -> WORK_DIR
if work_dir_arg and work_dir_arg.isdigit():
    idx = int(work_dir_arg)
    work_dir = PROJECTS[idx] if 0 <= idx < len(PROJECTS) else WORK_DIR
else:
    work_dir = work_dir_arg if work_dir_arg else WORK_DIR

def create_worktree(project_path, session_name):
    """Create git worktree in central ~/projects/aiosWorktrees/"""
    os.makedirs(WORKTREES_DIR, exist_ok=True)
    project_name = os.path.basename(project_path)
    worktree_name = f"{project_name}-{session_name}"
    worktree_path = os.path.join(WORKTREES_DIR, worktree_name)

    result = sp.run(['git', '-C', project_path, 'branch', '--show-current'],
                    capture_output=True, text=True)
    branch = result.stdout.strip() or 'main'

    result = sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', f"wt-{worktree_name}", worktree_path, branch],
                    capture_output=True, text=True)

    if result.returncode == 0:
        return worktree_path
    else:
        print(f"✗ Failed to create worktree: {result.stderr.strip()}")
        return None

# Handle launching terminal in directory without session
if new_window and not arg:
    launch_terminal_in_dir(work_dir)
    sys.exit(0)

if not arg:
    print(f"""mon.py - tmux session manager

Sessions:  h=htop  t=top  g=gemini  c=codex  l=claude
Prompts:   gp=gemini+prompt  cp=codex+prompt  lp=claude+prompt

Usage:
  ./mon.py <key>           Attach to session (create if needed)
  ./mon.py <key> -w        Attach in NEW terminal window
  ./mon.py +<key>          Create NEW instance with timestamp
  ./mon.py ++<key>         Create NEW instance with git worktree
  ./mon.py <key> <dir>     Start session in custom directory
  ./mon.py <key> <#>       Start session in saved project (#=0-{len(PROJECTS)-1})
  ./mon.py -w [dir/#]      Open NEW terminal in directory (no session)
  ./mon.py p               List saved projects
  ./mon.py ls              List all sessions
  ./mon.py x               Kill all sessions

Flags:
  -w, --new-window         Launch in new terminal window

Terminals:
  Supported: gnome-terminal, alacritty
  Auto-detects available terminal

Working Directory:
  Default: {WORK_DIR}

Saved Projects (edit at line 11):""")
    for i, proj in enumerate(PROJECTS):
        exists = "✓" if os.path.exists(proj) else "✗"
        print(f"  {i}. {exists} {proj}")
    print(f"""
Examples:
  ./mon.py c 0             Launch codex in project 0
  ./mon.py c 0 -w          Launch codex in NEW window
  ./mon.py -w 0            Open terminal in project 0 (no session)
  ./mon.py -w /tmp         Open terminal in /tmp
  ./mon.py +c 0            New codex instance in project 0
  ./mon.py ++c 0           New codex with worktree
  ./mon.py l 2 -w          Launch claude in new window

Git Worktrees:
  ++ prefix creates worktree in {WORKTREES_DIR}/<project>-<session>/
  Creates new branch: wt-<project>-<session>
  Example: ~/projects/aiosWorktrees/aios-codex-223045/""")
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
    key = arg[2:]
    if key in sessions and work_dir_arg and work_dir_arg.isdigit():
        idx = int(work_dir_arg)
        if 0 <= idx < len(PROJECTS):
            project_path = PROJECTS[idx]
            base_name, cmd = sessions[key]
            ts = datetime.now().strftime('%H%M%S')
            name = f"{base_name}-{ts}"

            if worktree_path := create_worktree(project_path, name):
                print(f"✓ Created worktree: {worktree_path}")
                sp.run(['tmux', 'new', '-d', '-s', name, '-c', worktree_path, cmd])

                if new_window:
                    launch_in_new_window(name)
                else:
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

        if new_window:
            launch_in_new_window(name)
        else:
            os.execvp('tmux', ['tmux', 'switch-client' if "TMUX" in os.environ else 'attach', '-t', name])
else:
    name, cmd = sessions.get(arg, (arg, None))
    sp.run(['tmux', 'new', '-d', '-s', name, '-c', work_dir, cmd or arg], capture_output=True)

    if new_window:
        launch_in_new_window(name)
    else:
        os.execvp('tmux', ['tmux', 'switch-client' if "TMUX" in os.environ else 'attach', '-t', name])
