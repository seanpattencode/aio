#!/usr/bin/env python3
import os, sys, subprocess as sp
import sqlite3
from datetime import datetime

# Database setup
DATA_DIR = os.path.expanduser("~/.local/share/aios")
DB_PATH = os.path.join(DATA_DIR, "mon.db")

class WALManager:
    """Context manager for SQLite database with WAL mode enabled."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()
        return False

def init_database():
    """Initialize database with schema and default values."""
    os.makedirs(DATA_DIR, exist_ok=True)

    with WALManager(DB_PATH) as conn:
        with conn:
            # Create tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    display_order INTEGER NOT NULL UNIQUE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    command_template TEXT NOT NULL
                )
            """)

            # Check if config exists
            cursor = conn.execute("SELECT COUNT(*) FROM config")
            if cursor.fetchone()[0] == 0:
                # Insert default config
                conn.execute("INSERT INTO config VALUES ('claude_prompt', 'tell me a joke')")
                conn.execute("INSERT INTO config VALUES ('codex_prompt', 'tell me a joke')")
                conn.execute("INSERT INTO config VALUES ('gemini_prompt', 'tell me a joke')")
                conn.execute("INSERT INTO config VALUES ('worktrees_dir', ?)",
                           (os.path.expanduser("~/projects/aiosWorktrees"),))

            # Check if projects exist
            cursor = conn.execute("SELECT COUNT(*) FROM projects")
            if cursor.fetchone()[0] == 0:
                # Insert default projects
                default_projects = [
                    os.path.expanduser("~/projects/aios"),
                    os.path.expanduser("~/projects/waylandauto"),
                    os.path.expanduser("~/AndroidStudioProjects/Workcycle"),
                    os.path.expanduser("~/projects/testRepoPrivate")
                ]
                for i, path in enumerate(default_projects):
                    conn.execute("INSERT INTO projects (path, display_order) VALUES (?, ?)",
                               (path, i))

            # Check if sessions exist
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            if cursor.fetchone()[0] == 0:
                # Insert default sessions
                default_sessions = [
                    ('h', 'htop', 'htop'),
                    ('t', 'top', 'top'),
                    ('g', 'gemini', 'gemini --yolo'),
                    ('gp', 'gemini-p', 'gemini --yolo "{GEMINI_PROMPT}"'),
                    ('c', 'codex', 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox'),
                    ('cp', 'codex-p', 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox "{CODEX_PROMPT}"'),
                    ('l', 'claude', 'claude --dangerously-skip-permissions'),
                    ('lp', 'claude-p', 'claude --dangerously-skip-permissions "{CLAUDE_PROMPT}"')
                ]
                for key, name, cmd in default_sessions:
                    conn.execute("INSERT INTO sessions VALUES (?, ?, ?)", (key, name, cmd))

def load_config():
    """Load configuration from database."""
    with WALManager(DB_PATH) as conn:
        cursor = conn.execute("SELECT key, value FROM config")
        config = dict(cursor.fetchall())
    return config

def load_projects():
    """Load projects from database."""
    with WALManager(DB_PATH) as conn:
        cursor = conn.execute("SELECT path FROM projects ORDER BY display_order")
        projects = [row[0] for row in cursor.fetchall()]
    return projects

def load_sessions(config):
    """Load sessions from database and substitute prompt values."""
    with WALManager(DB_PATH) as conn:
        cursor = conn.execute("SELECT key, name, command_template FROM sessions")
        sessions_data = cursor.fetchall()

    sessions = {}
    for key, name, cmd_template in sessions_data:
        # Substitute prompt placeholders
        cmd = cmd_template.format(
            CLAUDE_PROMPT=config.get('claude_prompt', 'tell me a joke'),
            CODEX_PROMPT=config.get('codex_prompt', 'tell me a joke'),
            GEMINI_PROMPT=config.get('gemini_prompt', 'tell me a joke')
        )
        sessions[key] = (name, cmd)

    return sessions

# Initialize database on first run
init_database()

# Load configuration from database
config = load_config()
CLAUDE_PROMPT = config.get('claude_prompt', 'tell me a joke')
CODEX_PROMPT = config.get('codex_prompt', 'tell me a joke')
GEMINI_PROMPT = config.get('gemini_prompt', 'tell me a joke')
WORK_DIR = os.getcwd()
WORKTREES_DIR = config.get('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees"))

PROJECTS = load_projects()
sessions = load_sessions(config)

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

def is_pane_receiving_output(session_name, threshold=10):
    """Check if a tmux pane had activity recently (tmux-style timestamp check).

    Uses tmux's built-in activity tracking - same method tmux uses internally.
    Returns True if activity occurred within threshold seconds.
    """
    import time

    # Get last activity timestamp from tmux
    result = sp.run(['tmux', 'display-message', '-p', '-t', session_name,
                     '#{window_activity}'],
                    capture_output=True, text=True)

    if result.returncode != 0:
        return False

    try:
        last_activity = int(result.stdout.strip())
        current_time = int(time.time())
        time_since_activity = current_time - last_activity

        # Active if had activity within threshold seconds
        return time_since_activity < threshold
    except (ValueError, AttributeError):
        return False

def get_session_for_worktree(worktree_path):
    """Find tmux session attached to a worktree path."""
    # Get all sessions
    result = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'],
                    capture_output=True, text=True)
    if result.returncode != 0:
        return None

    sessions = result.stdout.strip().split('\n')

    # Check each session's current path
    for session in sessions:
        if not session:
            continue
        path_result = sp.run(['tmux', 'display-message', '-p', '-t', session,
                             '#{pane_current_path}'],
                            capture_output=True, text=True)
        if path_result.returncode == 0:
            session_path = path_result.stdout.strip()
            # Check if session is in this worktree
            if session_path == worktree_path or session_path.startswith(worktree_path + '/'):
                return session

    return None

def list_jobs():
    """List all jobs (any directory with a session, plus worktrees) with their status."""
    # Get all tmux sessions and their directories
    result = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'],
                    capture_output=True, text=True)

    jobs_by_path = {}  # path -> list of sessions

    if result.returncode == 0:
        sessions = [s for s in result.stdout.strip().split('\n') if s]

        # Get directory for each session
        for session in sessions:
            path_result = sp.run(['tmux', 'display-message', '-p', '-t', session,
                                 '#{pane_current_path}'],
                                capture_output=True, text=True)
            if path_result.returncode == 0:
                session_path = path_result.stdout.strip()
                if session_path not in jobs_by_path:
                    jobs_by_path[session_path] = []
                jobs_by_path[session_path].append(session)

    # Also include worktrees without sessions
    if os.path.exists(WORKTREES_DIR):
        for item in os.listdir(WORKTREES_DIR):
            worktree_path = os.path.join(WORKTREES_DIR, item)
            if os.path.isdir(worktree_path) and worktree_path not in jobs_by_path:
                jobs_by_path[worktree_path] = []

    if not jobs_by_path:
        print("No jobs found")
        return

    print("Jobs:\n")

    # Sort by path
    for job_path in sorted(jobs_by_path.keys()):
        sessions_in_job = jobs_by_path[job_path]

        # Determine if this is a worktree
        is_worktree = job_path.startswith(WORKTREES_DIR)
        job_name = os.path.basename(job_path)

        # Check if any session is actively outputting
        is_active = False
        if sessions_in_job:
            for session in sessions_in_job:
                if is_pane_receiving_output(session):
                    is_active = True
                    break

        # Determine status display
        if not sessions_in_job:
            status_display = "📋 REVIEW"
            session_info = "(no session)"
        elif is_active:
            status_display = "🏃 RUNNING"
            if len(sessions_in_job) == 1:
                session_info = f"(session: {sessions_in_job[0]})"
            else:
                session_info = f"({len(sessions_in_job)} sessions: {', '.join(sessions_in_job)})"
        else:
            status_display = "📋 REVIEW"
            if len(sessions_in_job) == 1:
                session_info = f"(session: {sessions_in_job[0]})"
            else:
                session_info = f"({len(sessions_in_job)} sessions: {', '.join(sessions_in_job)})"

        # Add worktree indicator
        type_indicator = " [worktree]" if is_worktree else ""

        print(f"  {status_display}  {job_name}{type_indicator}")
        print(f"           {session_info}")
        print(f"           {job_path}")
        print()

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

    # Confirmation prompt
    print(f"\nWorktree: {worktree_name}")
    print(f"Path: {worktree_path}")
    print(f"Project: {project_path}")
    if push:
        print(f"Action: Remove worktree, delete branch, AND PUSH to remote")
        if commit_msg:
            print(f"Commit message: {commit_msg}")
    else:
        print(f"Action: Remove worktree and delete branch (no push)")

    response = input("\nAre you sure? (y/n): ").strip().lower()
    if response not in ['y', 'yes']:
        print("✗ Cancelled")
        return False

    print(f"\nRemoving worktree: {worktree_name}")

    # Git worktree remove (with --force to handle modified/untracked files)
    result = sp.run(['git', '-C', project_path, 'worktree', 'remove', '--force', worktree_path],
                    capture_output=True, text=True)

    if result.returncode != 0:
        print(f"✗ Failed to remove worktree: {result.stderr.strip()}")
        return False

    print(f"✓ Removed git worktree")

    # Delete branch (git worktree remove might have already deleted it)
    branch_name = f"wt-{worktree_name}"
    result = sp.run(['git', '-C', project_path, 'branch', '-D', branch_name],
                    capture_output=True, text=True)

    if result.returncode == 0:
        print(f"✓ Deleted branch: {branch_name}")
    elif 'not found' not in result.stderr:
        # Only show warning if it's not just "branch not found"
        print(f"⚠ Branch deletion: {result.stderr.strip()}")

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

# Check if arg is actually a directory/number (not a session key or worktree command)
is_directory_only = new_window and arg and not arg.startswith('+') and not arg.startswith('w') and arg not in sessions

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
  ./mon.py jobs            List all jobs (directories with sessions + worktrees)
  ./mon.py x               Kill all sessions

Worktrees:
  ./mon.py w               List all worktrees
  ./mon.py w<#/name>       Open worktree in current terminal
  ./mon.py w<#/name> -w    Open worktree in NEW window
  ./mon.py w- <#/name>     Remove worktree (git + delete)
  ./mon.py w-- <#/name>    Remove worktree, commit, and push (default msg)
  ./mon.py w-- <#/name> "Custom message"  Same but with custom commit message

Git Operations (works in ANY directory):
  ./mon.py push            Commit all changes and push (default message)
  ./mon.py push "msg"      Commit all changes and push with custom message

Flags:
  -w, --new-window         Launch in new terminal window

Terminals:
  Supported: gnome-terminal, alacritty
  Auto-detects available terminal

Working Directory:
  Default: {WORK_DIR}

Saved Projects (stored in database: {DB_PATH}):""")
    for i, proj in enumerate(PROJECTS):
        exists = "✓" if os.path.exists(proj) else "✗"
        print(f"  {i}. {exists} {proj}")
    print(f"""
Examples:
  ./mon.py c 0             Launch codex in project 0
  ./mon.py c 0 -w          Launch codex in NEW window
  ./mon.py -w 0            Open terminal in project 0
  ./mon.py ++c 0           New codex with worktree
  ./mon.py jobs            Show all active work (sessions + worktrees) with status
  ./mon.py w               List all worktrees
  ./mon.py w0              Open worktree #0
  ./mon.py w0 -w           Open worktree #0 in new window
  ./mon.py w- codex-123    Remove worktree matching 'codex-123'
  ./mon.py w-- 0           Remove worktree #0 and push (default message)
  ./mon.py w-- 0 "Cleanup experimental feature"  Remove and push with custom message
  ./mon.py push            Quick commit+push in current directory
  ./mon.py push "Fix bug in authentication"  Commit+push with custom message

Worktrees Location: {WORKTREES_DIR}

Note: The 'push' command works in ANY git repository, not just worktrees.
      Run from any directory to quickly commit and push your changes.""")
elif arg == 'jobs':
    list_jobs()
elif arg == 'p':
    print("Saved Projects:")
    for i, proj in enumerate(PROJECTS):
        exists = "✓" if os.path.exists(proj) else "✗"
        print(f"  {i}. {exists} {proj}")
elif arg == 'ls':
    # List sessions with their directories
    result = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'],
                    capture_output=True, text=True)

    if result.returncode != 0:
        print("No tmux sessions found")
        sys.exit(0)

    sessions_list = result.stdout.strip().split('\n')
    if not sessions_list or sessions_list == ['']:
        print("No tmux sessions found")
        sys.exit(0)

    print("Tmux Sessions:\n")
    for session in sessions_list:
        # Get session info (windows, attached, created time)
        info_result = sp.run(['tmux', 'list-sessions', '-F',
                             '#{session_name}:#{session_windows} windows#{?session_attached, (attached),}'],
                            capture_output=True, text=True)

        # Get current path of the session
        path_result = sp.run(['tmux', 'display-message', '-p', '-t', session,
                             '#{pane_current_path}'],
                            capture_output=True, text=True)

        # Extract info for this specific session
        session_info = [line for line in info_result.stdout.strip().split('\n')
                       if line.startswith(session + ':')]

        if session_info and path_result.returncode == 0:
            info = session_info[0].split(':', 1)[1] if ':' in session_info[0] else ''
            path = path_result.stdout.strip()
            print(f"  {session}: {info}")
            print(f"    └─ {path}")
        else:
            print(f"  {session}")
elif arg == 'x':
    sp.run(['tmux', 'kill-server'])
    print("✓ All sessions killed")
elif arg == 'push':
    # Quick commit and push in current directory
    cwd = os.getcwd()

    # Check if git repo
    result = sp.run(['git', '-C', cwd, 'rev-parse', '--git-dir'], capture_output=True)
    if result.returncode != 0:
        print("✗ Not a git repository")
        sys.exit(1)

    # Get commit message
    commit_msg = work_dir_arg if work_dir_arg else f"Update {os.path.basename(cwd)}"

    # Add all changes
    sp.run(['git', '-C', cwd, 'add', '-A'])

    # Commit
    result = sp.run(['git', '-C', cwd, 'commit', '-m', commit_msg],
                    capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✓ Committed: {commit_msg}")
    elif 'nothing to commit' in result.stdout:
        print("ℹ Nothing to commit")
    else:
        print(f"✗ Commit failed: {result.stderr.strip()}")
        sys.exit(1)

    # Push
    result = sp.run(['git', '-C', cwd, 'push'], capture_output=True, text=True)
    if result.returncode == 0:
        print("✓ Pushed to remote")
    else:
        print(f"✗ Push failed: {result.stderr.strip()}")
        sys.exit(1)
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
