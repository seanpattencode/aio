#!/usr/bin/env python3
import os, sys, subprocess as sp
import sqlite3
from datetime import datetime
import pexpect

# Auto-update: Pull latest version from git repo
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def auto_update():
    """Auto-update script from git repository if available."""
    # Check if we're in a git repo
    result = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', '--git-dir'],
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    if result.returncode != 0:
        return  # Not in a git repo, skip update

    # Get current commit hash
    before = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', 'HEAD'],
                    capture_output=True, text=True)

    if before.returncode != 0:
        return

    before_hash = before.stdout.strip()

    # Pull latest changes (fast-forward only, silent)
    sp.run(['git', '-C', SCRIPT_DIR, 'pull', '--ff-only'],
           stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    # Get new commit hash
    after = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', 'HEAD'],
                   capture_output=True, text=True)

    if after.returncode != 0:
        return

    after_hash = after.stdout.strip()

    # If updated, re-exec with same arguments
    if before_hash != after_hash:
        os.execv(sys.executable, [sys.executable, __file__] + sys.argv[1:])

# Run auto-update before anything else
auto_update()

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

def run_with_expect(command, expectations, timeout=30, cwd=None, echo=True):
    """Run command with expect-style pattern matching and auto-responses.

    Args:
        command: Command string or list to execute
        expectations: List of (pattern, response) tuples or dict with patterns as keys
        timeout: Timeout in seconds for each expect operation
        cwd: Working directory for command
        echo: Whether to echo output to stdout

    Returns:
        (exit_code, output) tuple

    Example:
        run_with_expect(
            'git push',
            [('Username:', 'myuser\\n'),
             ('Password:', 'mypass\\n')]
        )
    """
    try:
        # Convert expectations dict to list if needed
        if isinstance(expectations, dict):
            expectations = list(expectations.items())

        # Spawn the process
        if isinstance(command, str):
            child = pexpect.spawn(command, cwd=cwd, encoding='utf-8', timeout=timeout)
        else:
            child = pexpect.spawn(command[0], command[1:], cwd=cwd, encoding='utf-8', timeout=timeout)

        output = []

        # Process expectations
        while True:
            # Build pattern list for expect
            patterns = [pattern for pattern, _ in expectations]
            patterns.append(pexpect.EOF)
            patterns.append(pexpect.TIMEOUT)

            try:
                index = child.expect(patterns, timeout=timeout)

                # Capture what we've seen so far
                if child.before:
                    output.append(child.before)
                    if echo:
                        print(child.before, end='')

                # Check if we hit EOF or TIMEOUT
                if index == len(expectations):  # EOF
                    if child.after and child.after != pexpect.EOF:
                        output.append(str(child.after))
                        if echo:
                            print(child.after, end='')
                    break
                elif index == len(expectations) + 1:  # TIMEOUT
                    # Just break on timeout, process might be done
                    break
                else:
                    # Found a pattern, send the response
                    _, response = expectations[index]
                    if response:
                        child.sendline(response)

            except pexpect.EOF:
                break
            except pexpect.TIMEOUT:
                break

        # Get remaining output
        try:
            remaining = child.read()
            if remaining:
                output.append(remaining)
                if echo:
                    print(remaining, end='')
        except:
            pass

        # Wait for process to finish
        child.close()

        return (child.exitstatus or 0, ''.join(output))

    except Exception as e:
        print(f"✗ Error running command: {e}")
        return (1, str(e))

def watch_tmux_session(session_name, expectations, duration=None):
    """Watch a tmux session and auto-respond to patterns.

    Args:
        session_name: Name of tmux session to watch
        expectations: Dict of {pattern: response} or list of (pattern, response) tuples
        duration: How long to watch (None = watch once and exit)

    Example:
        watch_tmux_session('codex', {
            'Are you sure?': 'y',
            'Continue?': 'yes'
        })
    """
    import time
    import re

    # Convert expectations to dict if needed
    if isinstance(expectations, (list, tuple)):
        expectations = dict(expectations)

    # Compile patterns for efficiency
    compiled_patterns = {re.compile(pattern): response
                        for pattern, response in expectations.items()}

    last_content = ""
    start_time = time.time()

    while True:
        # Check if duration exceeded
        if duration and (time.time() - start_time) > duration:
            break

        # Capture current pane content
        result = sp.run(['tmux', 'capture-pane', '-t', session_name, '-p'],
                       capture_output=True, text=True)

        if result.returncode != 0:
            print(f"✗ Session {session_name} not found")
            return False

        current_content = result.stdout

        # Check if content changed
        if current_content != last_content:
            # Look for patterns in new content
            for pattern, response in compiled_patterns.items():
                if pattern.search(current_content):
                    # Found a pattern, send response
                    sp.run(['tmux', 'send-keys', '-t', session_name, response, 'Enter'])
                    print(f"✓ Auto-responded to pattern: {pattern.pattern}")

                    # If no duration specified, exit after first response
                    if duration is None:
                        return True

            last_content = current_content

        # Small delay to avoid hammering tmux
        time.sleep(0.1)

    return True

def wait_for_agent_ready(session_name, timeout=5):
    """Wait for AI agent to be ready to receive input.

    Uses pattern matching (like pexpect) to detect agent prompt patterns.

    Args:
        session_name: Name of tmux session
        timeout: Max seconds to wait

    Returns:
        True if agent is ready, False if timeout
    """
    import time
    import re

    # Agent-specific ready patterns (regex)
    # These patterns ensure the agent is fully initialized and waiting for input
    ready_patterns = [
        r'›.*\n\n\s+\d+%\s+context left',      # Codex prompt with context indicator
        r'>\s+Type your message',              # Gemini input prompt
        r'gemini-2\.5-pro.*\(\d+%\)',          # Gemini status line
        r'──+\s*\n>\s+\w+',                    # Claude prompt (separator + prompt with text)
    ]

    compiled_patterns = [re.compile(p, re.MULTILINE) for p in ready_patterns]

    start_time = time.time()
    last_content = ""

    while (time.time() - start_time) < timeout:
        # Capture pane content
        result = sp.run(['tmux', 'capture-pane', '-t', session_name, '-p'],
                       capture_output=True, text=True)

        if result.returncode != 0:
            return False

        current_content = result.stdout

        # Check if content changed (agent is loading)
        if current_content != last_content:
            # Check for ready patterns
            for pattern in compiled_patterns:
                if pattern.search(current_content):
                    return True

            last_content = current_content

        time.sleep(0.2)

    # Timeout - try sending anyway
    return True

def send_prompt_to_session(session_name, prompt, wait_for_completion=False, timeout=None, wait_for_ready=True):
    """Send a prompt to a tmux session.

    Args:
        session_name: Name of tmux session
        prompt: Text to send to the session
        wait_for_completion: If True, wait for activity to stop before returning
        timeout: Max seconds to wait for completion (only used if wait_for_completion=True)
        wait_for_ready: If True, wait for agent to be ready before sending

    Returns:
        True if successful, False otherwise

    Example:
        send_prompt_to_session('codex', 'create a test.txt file with hello world')
    """
    import time

    # Check if session exists
    result = sp.run(['tmux', 'has-session', '-t', session_name],
                   capture_output=True)
    if result.returncode != 0:
        print(f"✗ Session {session_name} not found")
        return False

    # Wait for agent to be ready
    if wait_for_ready:
        print(f"⏳ Waiting for agent to be ready...", end='', flush=True)
        if wait_for_agent_ready(session_name):
            print(" ✓")
        else:
            print(" (timeout, sending anyway)")

    # Send the prompt and Enter separately for reliability
    sp.run(['tmux', 'send-keys', '-t', session_name, prompt])
    time.sleep(0.1)  # Brief delay before Enter for terminal processing
    sp.run(['tmux', 'send-keys', '-t', session_name, 'Enter'])
    print(f"✓ Sent prompt to session '{session_name}'")

    if wait_for_completion:
        print("⏳ Waiting for completion...", end='', flush=True)
        start_time = time.time()
        last_active = time.time()
        idle_threshold = 3  # seconds of inactivity to consider "done"

        while True:
            # Check if timeout exceeded
            if timeout and (time.time() - start_time) > timeout:
                print(f"\n⚠ Timeout ({timeout}s) reached")
                return True

            # Check if session is active
            is_active = is_pane_receiving_output(session_name, threshold=2)

            if is_active:
                last_active = time.time()
                print(".", end='', flush=True)
            else:
                # Check if idle for long enough
                if (time.time() - last_active) > idle_threshold:
                    print("\n✓ Completed (activity stopped)")
                    return True

            time.sleep(0.5)

    return True

def get_or_create_directory_session(session_key, target_dir):
    """Find existing session for directory or create new one.

    Returns session name to attach to.
    """
    if session_key not in sessions:
        return None

    base_name, cmd_template = sessions[session_key]

    # First, check if there's already a session in this directory
    result = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'],
                    capture_output=True, text=True)

    if result.returncode == 0:
        existing_sessions = [s for s in result.stdout.strip().split('\n') if s]

        # Check each session's current path
        for session in existing_sessions:
            # Only check sessions that match our base name pattern
            if not (session == base_name or session.startswith(base_name + '-')):
                continue

            path_result = sp.run(['tmux', 'display-message', '-p', '-t', session,
                                 '#{pane_current_path}'],
                                capture_output=True, text=True)
            if path_result.returncode == 0:
                session_path = path_result.stdout.strip()
                if session_path == target_dir:
                    # Found existing session in this directory!
                    return session

    # No existing session in this directory, create new one
    # Use directory name to make it unique
    dir_name = os.path.basename(target_dir)
    session_name = f"{base_name}-{dir_name}"

    # If that session name is taken (in a different directory), add a suffix
    attempt = 0
    final_session_name = session_name
    while True:
        check_result = sp.run(['tmux', 'has-session', '-t', final_session_name],
                             capture_output=True)
        if check_result.returncode != 0:
            # Session doesn't exist, we can use this name
            break

        # Session exists, try with suffix
        attempt += 1
        final_session_name = f"{session_name}-{attempt}"

    return final_session_name

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

        # Add copy-pastable commands
        print()

        # Command to open directory in new window
        if is_worktree:
            # For worktrees, show the 'w' command if possible
            worktrees_list = sorted([d for d in os.listdir(WORKTREES_DIR)
                                    if os.path.isdir(os.path.join(WORKTREES_DIR, d))])
            if job_name in worktrees_list:
                worktree_index = worktrees_list.index(job_name)
                print(f"           Open dir:  mon w{worktree_index} -w")
            else:
                print(f"           Open dir:  mon -w {job_path}")
        else:
            print(f"           Open dir:  mon -w {job_path}")

        # Command to attach to session(s)
        if sessions_in_job:
            if len(sessions_in_job) == 1:
                print(f"           Attach:    tmux attach -t {sessions_in_job[0]}")
            else:
                # Show all sessions
                for session in sessions_in_job:
                    print(f"           Attach:    tmux attach -t {session}")

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

def remove_worktree(worktree_path, push=False, commit_msg=None, skip_confirm=False):
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
        print(f"Action: Remove worktree, delete branch, switch to main, AND PUSH to main branch")
        if commit_msg:
            print(f"Commit message: {commit_msg}")
    else:
        print(f"Action: Remove worktree and delete branch (no push)")

    if not skip_confirm:
        response = input("\nAre you sure? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            print("✗ Cancelled")
            return False
    else:
        print("\n⚠ Confirmation skipped (--yes flag)")

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

        # Detect main branch name (main or master)
        result = sp.run(['git', '-C', project_path, 'symbolic-ref', 'refs/remotes/origin/HEAD'],
                        capture_output=True, text=True)
        if result.returncode == 0:
            main_branch = result.stdout.strip().replace('refs/remotes/origin/', '')
        else:
            # Fallback: try 'main' first, then 'master'
            result = sp.run(['git', '-C', project_path, 'rev-parse', '--verify', 'main'],
                           capture_output=True)
            main_branch = 'main' if result.returncode == 0 else 'master'

        print(f"→ Switching to {main_branch} branch...")

        # Switch to main branch
        result = sp.run(['git', '-C', project_path, 'checkout', main_branch],
                        capture_output=True, text=True)

        if result.returncode != 0:
            print(f"✗ Failed to switch to {main_branch}: {result.stderr.strip()}")
            return True

        print(f"✓ Switched to {main_branch}")

        # Check if there are changes to commit
        result = sp.run(['git', '-C', project_path, 'status', '--porcelain'],
                        capture_output=True, text=True)

        if result.stdout.strip():
            # Commit changes
            sp.run(['git', '-C', project_path, 'add', '-A'])
            sp.run(['git', '-C', project_path, 'commit', '-m', commit_msg])
            print(f"✓ Committed changes: {commit_msg}")

        # Push to main
        result = sp.run(['git', '-C', project_path, 'push', 'origin', main_branch],
                        capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✓ Pushed to {main_branch}")
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
# Also determine if work_dir_arg is actually a prompt (for later)
is_work_dir_a_prompt = False

if work_dir_arg and work_dir_arg.isdigit():
    idx = int(work_dir_arg)
    work_dir = PROJECTS[idx] if 0 <= idx < len(PROJECTS) else WORK_DIR
elif work_dir_arg and os.path.isdir(os.path.expanduser(work_dir_arg)):
    # It's a valid directory path
    work_dir = work_dir_arg
elif work_dir_arg:
    # Not a digit, not a directory - likely a prompt
    is_work_dir_a_prompt = True
    work_dir = WORK_DIR
else:
    work_dir = WORK_DIR

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

# Handle project number shortcut: mon 1, mon 2, etc.
if arg and arg.isdigit() and not work_dir_arg:
    project_idx = int(arg)
    if 0 <= project_idx < len(PROJECTS):
        project_path = PROJECTS[project_idx]
        print(f"📂 Opening project {project_idx}: {project_path}")
        os.chdir(project_path)
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    else:
        print(f"✗ Invalid project index: {project_idx}")
        print(f"   Valid range: 0-{len(PROJECTS)-1}")
        sys.exit(1)

# Handle worktree commands (but not 'watch')
if arg and arg.startswith('w') and arg != 'watch':
    if arg == 'w':
        # List worktrees
        list_worktrees()
        sys.exit(0)
    elif arg.startswith('w--'):
        # Remove and push
        pattern = work_dir_arg
        commit_msg = None
        skip_confirm = '--yes' in sys.argv or '-y' in sys.argv

        # Parse remaining args for commit message
        for i in range(3, len(sys.argv)):
            if sys.argv[i] not in ['--yes', '-y']:
                commit_msg = sys.argv[i]
                break

        if not pattern:
            print("✗ Usage: ./mon.py w-- <worktree#/name> [commit message] [--yes/-y]")
            sys.exit(1)

        worktree_path = find_worktree(pattern)
        if worktree_path:
            remove_worktree(worktree_path, push=True, commit_msg=commit_msg, skip_confirm=skip_confirm)
        else:
            print(f"✗ Worktree not found: {pattern}")
        sys.exit(0)
    elif arg.startswith('w-'):
        # Remove only
        pattern = work_dir_arg
        skip_confirm = '--yes' in sys.argv or '-y' in sys.argv

        if not pattern:
            print("✗ Usage: ./mon.py w- <worktree#/name> [--yes/-y]")
            sys.exit(1)

        worktree_path = find_worktree(pattern)
        if worktree_path:
            remove_worktree(worktree_path, push=False, skip_confirm=skip_confirm)
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
  ./mon.py <#>             Open project in current terminal (no session)
  ./mon.py -w [dir/#]      Open NEW terminal in directory (no session)
  ./mon.py p               List saved projects
  ./mon.py ls              List all sessions
  ./mon.py jobs            List all jobs (directories with sessions + worktrees)
  ./mon.py watch <session> Watch session and auto-respond to prompts
  ./mon.py watch <session> 60  Watch for 60 seconds
  ./mon.py x               Kill all sessions
  ./mon.py install         Install as 'mon' command (callable from anywhere)

Worktrees:
  ./mon.py w               List all worktrees
  ./mon.py w<#/name>       Open worktree in current terminal
  ./mon.py w<#/name> -w    Open worktree in NEW window
  ./mon.py w- <#/name>     Remove worktree (git + delete)
  ./mon.py w- <#/name> -y  Remove worktree without confirmation
  ./mon.py w-- <#/name>    Remove worktree, switch to main, commit, and push to main
  ./mon.py w-- <#/name> --yes  Remove and push to main without confirmation
  ./mon.py w-- <#/name> "Custom message"  Same but with custom commit message

Git Operations (works in ANY directory):
  ./mon.py push            Commit all changes and push (default message)
  ./mon.py push "msg"      Commit all changes and push with custom message

Automation (sending prompts to AI sessions):
  ./mon.py send <session> <prompt>        Send prompt to existing session
  ./mon.py send <session> <prompt> --wait Send prompt and wait for completion
  ./mon.py <key> <prompt>                 Create/attach session and send prompt
  ./mon.py <key> <dir> <prompt>           Create/attach in dir and send prompt

Multi-Agent Parallel Execution:
  ./mon.py multi <project#> c:3 g:1 <prompt>  Run 3 codex + 1 gemini in parallel
  ./mon.py multi <project#> c:2 l:1 <prompt>  Run 2 codex + 1 claude in parallel
  ./mon.py multi 3 c:4 "create tests"         Run 4 codex instances with same prompt

  Agent specs: c:N (codex), l:N (claude), g:N (gemini)
  Creates worktrees and sends prompts to all instances automatically

Flags:
  -w, --new-window         Launch in new terminal window
  --wait                   Wait for command completion (send command only)

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
  ./mon.py install         Install globally (then use 'mon' instead of './mon.py')
  ./mon.py 1               Open project 1 in current terminal
  ./mon.py c 0             Launch codex in project 0
  ./mon.py c 0 -w          Launch codex in NEW window
  ./mon.py -w 0            Open terminal in project 0 (new window)
  ./mon.py ++c 0           New codex with worktree
  ./mon.py jobs            Show all active work (sessions + worktrees) with status
  ./mon.py w               List all worktrees
  ./mon.py w0              Open worktree #0
  ./mon.py w0 -w           Open worktree #0 in new window
  ./mon.py w- codex-123    Remove worktree matching 'codex-123'
  ./mon.py w- 0 -y         Remove worktree #0 without confirmation
  ./mon.py w-- 0           Remove worktree #0, switch to main, and push to main
  ./mon.py w-- 0 --yes     Remove and push to main (skip confirmation)
  ./mon.py w-- 0 "Cleanup experimental feature"  Remove and push to main with custom message
  ./mon.py watch codex     Watch codex session and auto-respond to confirmations
  ./mon.py send codex "create a test file"  Send prompt to codex session
  ./mon.py send codex "list all files" --wait  Send and wait for completion
  ./mon.py c "create README.md"  Start codex and send prompt
  ./mon.py c 3 "fix the bug"  Start codex in project 3 and send prompt
  ./mon.py multi 3 c:3 g:1 "create a login feature"  Run 3 codex + 1 gemini in parallel
  ./mon.py push            Quick commit+push in current directory
  ./mon.py push "Fix bug in authentication"  Commit+push with custom message

Worktrees Location: {WORKTREES_DIR}

Notes:
  • Run './mon.py install' to use 'mon' globally from any directory
  • Auto-updates from git on each run (always latest version)
  • The 'push' command works in ANY git repository, not just worktrees
  • Use -y/--yes flags to skip interactive confirmations
  • Use 'watch' to auto-respond to prompts in running sessions (expect-based)
  • Use 'send' or pass prompts directly to automate AI agent tasks
  • Prompts are sent via tmux send-keys to running sessions""")
elif arg == 'install':
    # Install mon as a global command
    bin_dir = os.path.expanduser("~/.local/bin")
    mon_link = os.path.join(bin_dir, "mon")
    script_path = os.path.abspath(__file__)

    # Create bin directory if needed
    os.makedirs(bin_dir, exist_ok=True)

    # Remove existing symlink if present
    if os.path.exists(mon_link):
        if os.path.islink(mon_link):
            os.remove(mon_link)
            print(f"✓ Removed existing symlink: {mon_link}")
        else:
            print(f"✗ {mon_link} exists but is not a symlink. Please remove it manually.")
            sys.exit(1)

    # Create symlink
    os.symlink(script_path, mon_link)
    print(f"✓ Created symlink: {mon_link} -> {script_path}")

    # Check if ~/.local/bin is in PATH
    user_path = os.environ.get('PATH', '')
    if bin_dir not in user_path:
        print(f"\n⚠ Warning: {bin_dir} is not in your PATH")
        print(f"Add this line to your ~/.bashrc or ~/.zshrc:")
        print(f'  export PATH="$HOME/.local/bin:$PATH"')
        print(f"\nThen run: source ~/.bashrc (or restart your terminal)")
    else:
        print(f"\n✓ {bin_dir} is in your PATH")
        print(f"✓ You can now run 'mon' from anywhere!")

    print(f"\nThe script will auto-update from git on each run.")
elif arg == 'watch':
    # Watch a tmux session and auto-respond to patterns
    if not work_dir_arg:
        print("✗ Usage: mon watch <session_name> [duration_seconds]")
        print("\nExamples:")
        print("  mon watch codex          # Watch codex session, respond once and exit")
        print("  mon watch codex 60       # Watch codex session for 60 seconds")
        print("\nDefault patterns:")
        print("  'Are you sure?' -> 'y'")
        print("  'Continue?' -> 'yes'")
        print("  '[y/N]' -> 'y'")
        print("  '[Y/n]' -> 'y'")
        sys.exit(1)

    session_name = work_dir_arg
    duration = None

    # Check if duration provided
    if len(sys.argv) > 3:
        try:
            duration = int(sys.argv[3])
        except ValueError:
            print(f"✗ Invalid duration: {sys.argv[3]}")
            sys.exit(1)

    # Default expectations
    default_expectations = {
        r'Are you sure\?': 'y',
        r'Continue\?': 'yes',
        r'\[y/N\]': 'y',
        r'\[Y/n\]': 'y',
    }

    print(f"👁 Watching session '{session_name}'...")
    if duration:
        print(f"   Duration: {duration} seconds")
    else:
        print(f"   Mode: Auto-respond once and exit")

    result = watch_tmux_session(session_name, default_expectations, duration)
    if result:
        print("✓ Watch completed")
    else:
        sys.exit(1)
elif arg == 'send':
    # Send a prompt to an existing session
    if not work_dir_arg:
        print("✗ Usage: mon send <session_name> <prompt>")
        print("\nExamples:")
        print("  mon send codex 'create a test file'")
        print("  mon send claude-aios 'explain this code'")
        print("\nFlags:")
        print("  --wait    Wait for completion before returning")
        sys.exit(1)

    session_name = work_dir_arg
    wait = '--wait' in sys.argv

    # Get prompt from remaining args
    prompt_parts = []
    for i in range(3, len(sys.argv)):
        if sys.argv[i] == '--wait':
            continue
        prompt_parts.append(sys.argv[i])

    if not prompt_parts:
        print("✗ No prompt provided")
        sys.exit(1)

    prompt = ' '.join(prompt_parts)

    # Send the prompt
    result = send_prompt_to_session(session_name, prompt, wait_for_completion=wait, timeout=60)
    if not result:
        sys.exit(1)
elif arg == 'multi':
    # Run multiple agent instances in parallel worktrees
    # Usage: mon multi <project#> c:3 g:1 "prompt text"
    if not work_dir_arg or not work_dir_arg.isdigit():
        print("✗ Usage: mon multi <project#> <agent_specs>... <prompt>")
        print("\nExamples:")
        print("  mon multi 3 c:3 g:1 'create a test file'")
        print("  mon multi 0 c:2 l:1 'fix the bug'")
        print("\nAgent specs:")
        print("  c:N  - N codex instances")
        print("  l:N  - N claude instances")
        print("  g:N  - N gemini instances")
        sys.exit(1)

    project_idx = int(work_dir_arg)
    if not (0 <= project_idx < len(PROJECTS)):
        print(f"✗ Invalid project index: {project_idx}")
        sys.exit(1)

    project_path = PROJECTS[project_idx]

    # Parse agent specifications and prompt
    agent_specs = []
    prompt_parts = []
    parsing_agents = True

    for i in range(3, len(sys.argv)):
        arg_part = sys.argv[i]

        # Check if this looks like an agent spec (e.g., "c:3")
        if parsing_agents and ':' in arg_part and len(arg_part) <= 4:
            parts = arg_part.split(':')
            if len(parts) == 2 and parts[0] in ['c', 'l', 'g'] and parts[1].isdigit():
                agent_key = parts[0]
                count = int(parts[1])
                agent_specs.append((agent_key, count))
                continue

        # Everything else is part of the prompt
        parsing_agents = False
        prompt_parts.append(arg_part)

    if not agent_specs:
        print("✗ No agent specifications provided")
        sys.exit(1)

    if not prompt_parts:
        print("✗ No prompt provided")
        sys.exit(1)

    prompt = ' '.join(prompt_parts)

    # Calculate total instances
    total_instances = sum(count for _, count in agent_specs)

    print(f"🚀 Starting {total_instances} agent instances in parallel worktrees...")
    print(f"   Project: {project_path}")
    print(f"   Agents: {', '.join(f'{key}×{count}' for key, count in agent_specs)}")
    print(f"   Prompt: {prompt}")
    print()

    # Create worktrees and launch sessions
    launched_sessions = []

    for agent_key, count in agent_specs:
        base_name, cmd = sessions.get(agent_key, (None, None))

        if not base_name:
            print(f"✗ Unknown agent key: {agent_key}")
            continue

        for instance_num in range(count):
            # Create unique worktree name
            ts = datetime.now().strftime('%H%M%S')
            import time
            time.sleep(0.01)  # Ensure unique timestamps
            worktree_name = f"{base_name}-{ts}-{instance_num}"

            # Create worktree
            worktree_path = create_worktree(project_path, worktree_name)

            if not worktree_path:
                print(f"✗ Failed to create worktree for {base_name} instance {instance_num+1}")
                continue

            # Create tmux session in worktree
            session_name = worktree_name
            sp.run(['tmux', 'new', '-d', '-s', session_name, '-c', worktree_path, cmd],
                  capture_output=True)

            launched_sessions.append((session_name, base_name, instance_num+1))
            print(f"✓ Created {base_name} instance {instance_num+1}: {session_name}")

    if not launched_sessions:
        print("✗ No sessions were created")
        sys.exit(1)

    print(f"\n📤 Sending prompt to all {len(launched_sessions)} sessions...")

    # Send prompts to all sessions
    for session_name, agent_name, instance_num in launched_sessions:
        print(f"   → {agent_name} instance {instance_num}...", end=' ', flush=True)
        result = send_prompt_to_session(session_name, prompt, wait_for_ready=True, wait_for_completion=False)
        if result:
            print("✓")
        else:
            print("✗")

    print(f"\n✓ All sessions launched! Use 'mon jobs' to see status")
    print(f"   Session names: {', '.join(s[0] for s in launched_sessions)}")
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
    # Try directory-based session logic first
    session_name = get_or_create_directory_session(arg, work_dir)

    if session_name is None:
        # Not a known session key, use original behavior
        name, cmd = sessions.get(arg, (arg, None))
        sp.run(['tmux', 'new', '-d', '-s', name, '-c', work_dir, cmd or arg], capture_output=True)
        session_name = name
    else:
        # Got a directory-specific session name
        # Check if it exists, create if not
        check_result = sp.run(['tmux', 'has-session', '-t', session_name],
                             capture_output=True)
        if check_result.returncode != 0:
            # Session doesn't exist, create it
            _, cmd = sessions[arg]
            sp.run(['tmux', 'new', '-d', '-s', session_name, '-c', work_dir, cmd],
                  capture_output=True)

    # Check if there's a prompt to send (remaining args after session key and work_dir)
    # Determine where prompts start based on whether work_dir_arg was a directory or prompt
    if is_work_dir_a_prompt:
        # work_dir_arg itself is the start of the prompt
        prompt_start_idx = 2
    elif work_dir_arg:
        # work_dir_arg was a real directory/project, prompts start after it
        prompt_start_idx = 3
    else:
        # No work_dir_arg, prompts start at index 2
        prompt_start_idx = 2

    prompt_parts = []
    for i in range(prompt_start_idx, len(sys.argv)):
        if sys.argv[i] not in ['-w', '--new-window', '--yes', '-y']:
            prompt_parts.append(sys.argv[i])

    if prompt_parts:
        prompt = ' '.join(prompt_parts)
        print(f"📤 Sending prompt to session...")
        # send_prompt_to_session will wait for agent to be ready
        send_prompt_to_session(session_name, prompt, wait_for_completion=False, wait_for_ready=True)

    if new_window:
        launch_in_new_window(session_name)
    else:
        os.execvp('tmux', ['tmux', 'switch-client' if "TMUX" in os.environ else 'attach', '-t', session_name])
