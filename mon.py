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

def list_worktrees():
    """List all worktrees in central directory"""
    if not os.path.exists(WORKTREES_DIR):
        print(f"No worktrees found in {WORKTREES_DIR}")
        return []

    items = sorted(os.listdir(WORKTREES_DIR))
    if not items:
        print("No worktrees found")
        return []

    print(f"Worktrees in {WORKTREES_DIR}:\n")
    for i, item in enumerate(items):
        full_path = os.path.join(WORKTREES_DIR, item)
        if os.path.isdir(full_path):
            print(f"  {i}. {item}")
    return items

def find_worktree(pattern):
    """Find worktree by number or name pattern"""
    if not os.path.exists(WORKTREES_DIR):
        return None

    items = sorted(os.listdir(WORKTREES_DIR))

    # Check if pattern is a number
    if pattern.isdigit():
        idx = int(pattern)
        if 0 <= idx < len(items):
            return os.path.join(WORKTREES_DIR, items[idx])
        return None

    # Find by partial match
    matches = [item for item in items if pattern in item]
    if len(matches) == 1:
        return os.path.join(WORKTREES_DIR, matches[0])
    elif len(matches) > 1:
        print(f"✗ Multiple matches for '{pattern}':")
        for m in matches:
            print(f"  - {m}")
        return None

    return None

def get_project_for_worktree(worktree_path):
    """Determine which project a worktree belongs to"""
    worktree_name = os.path.basename(worktree_path)

    # Extract project name from worktree name (format: project-session-timestamp)
    for proj in PROJECTS:
        proj_name = os.path.basename(proj)
        if worktree_name.startswith(proj_name + '-'):
            return proj

    return None

def remove_worktree(worktree_path, push=False, commit_msg=None):
    """Remove worktree and optionally push changes"""
    if not os.path.exists(worktree_path):
        print(f"✗ Worktree does not exist: {worktree_path}")
        return False

    worktree_name = os.path.basename(worktree_path)
    project_path = get_project_for_worktree(worktree_path)

    if not project_path:
        print(f"✗ Could not determine project for worktree: {worktree_name}")
        return False

    print(f"Removing worktree: {worktree_name}")

    # Git worktree remove
    result = sp.run(['git', '-C', project_path, 'worktree', 'remove', worktree_path],
                    capture_output=True, text=True)

    if result.returncode != 0:
        print(f"✗ Failed to remove worktree: {result.stderr.strip()}")
        return False

    print(f"✓ Removed git worktree")

    # Delete branch
    branch_name = f"wt-{worktree_name}"
    result = sp.run(['git', '-C', project_path, 'branch', '-D', branch_name],
                    capture_output=True, text=True)

    if result.returncode == 0:
        print(f"✓ Deleted branch: {branch_name}")

    # Remove directory if still exists
    if os.path.exists(worktree_path):
        import shutil
        shutil.rmtree(worktree_path)
        print(f"✓ Deleted directory: {worktree_path}")

    # Push if requested
    if push:
        if not commit_msg:
            commit_msg = f"Remove worktree {worktree_name}"

        # Check if there are changes to commit
        result = sp.run(['git', '-C', project_path, 'status', '--porcelain'],
                        capture_output=True, text=True)

        if result.stdout.strip():
            # Commit changes
            sp.run(['git', '-C', project_path, 'add', '-A'])
            sp.run(['git', '-C', project_path, 'commit', '-m', commit_msg])
            print(f"✓ Committed changes: {commit_msg}")

        # Push
        result = sp.run(['git', '-C', project_path, 'push'],
                        capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✓ Pushed to remote")
        else:
            print(f"✗ Push failed: {result.stderr.strip()}")

    return True

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

# Handle worktree commands
if arg and arg.startswith('w'):
    if arg == 'w':
        # List worktrees
        list_worktrees()
        sys.exit(0)
    elif arg.startswith('w--'):
        # Remove and push
        pattern = work_dir_arg
        commit_msg = sys.argv[3] if len(sys.argv) > 3 else None

        if not pattern:
            print("✗ Usage: ./mon.py w-- <worktree#/name> [commit message]")
            sys.exit(1)

        worktree_path = find_worktree(pattern)
        if worktree_path:
            remove_worktree(worktree_path, push=True, commit_msg=commit_msg)
        else:
            print(f"✗ Worktree not found: {pattern}")
        sys.exit(0)
    elif arg.startswith('w-'):
        # Remove only
        pattern = work_dir_arg

        if not pattern:
            print("✗ Usage: ./mon.py w- <worktree#/name>")
            sys.exit(1)

        worktree_path = find_worktree(pattern)
        if worktree_path:
            remove_worktree(worktree_path, push=False)
        else:
            print(f"✗ Worktree not found: {pattern}")
        sys.exit(0)
    elif len(arg) > 1:
        # Open worktree - pattern is after 'w'
        pattern = arg[1:]
        worktree_path = find_worktree(pattern)

        if worktree_path:
            if new_window:
                launch_terminal_in_dir(worktree_path)
            else:
                os.chdir(worktree_path)
                os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
        else:
            print(f"✗ Worktree not found: {pattern}")
        sys.exit(0)

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

Worktrees:
  ./mon.py w               List all worktrees
  ./mon.py w<#/name>       Open worktree in current terminal
  ./mon.py w<#/name> -w    Open worktree in NEW window
  ./mon.py w- <#/name>     Remove worktree (git + delete)
  ./mon.py w-- <#/name>    Remove worktree and push
  ./mon.py w-- <#/name> "msg"  Remove, push with custom message

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
  ./mon.py -w 0            Open terminal in project 0
  ./mon.py ++c 0           New codex with worktree
  ./mon.py w               List all worktrees
  ./mon.py w0              Open worktree #0
  ./mon.py w0 -w           Open worktree #0 in new window
  ./mon.py w- codex-123    Remove worktree matching 'codex-123'
  ./mon.py w-- 0           Remove worktree #0 and push

Worktrees Location: {WORKTREES_DIR}""")
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
