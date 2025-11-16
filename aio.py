#!/usr/bin/env python3
import os, sys, subprocess as sp
import sqlite3
from datetime import datetime
from pathlib import Path
import pexpect
import shlex
import time

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
DB_PATH = os.path.join(DATA_DIR, "aio.db")

def backup_database(label="manual"):
    """Backup database using SQLite's .backup() method."""
    backup_path = os.path.join(DATA_DIR, f"aio_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    with sqlite3.connect(DB_PATH) as src, sqlite3.connect(backup_path) as dst:
        src.backup(dst)
    return backup_path

def restore_database(backup_path):
    """Restore database from backup using SQLite's .backup() method."""
    with sqlite3.connect(backup_path) as src, sqlite3.connect(DB_PATH) as dst:
        src.backup(dst)

def auto_backup_check():
    """Git-style auto-backup: fork subprocess if 10+ min passed, return immediately."""
    if not hasattr(os, 'fork'):
        return
    timestamp_file = os.path.join(DATA_DIR, ".backup_timestamp")
    if os.path.exists(timestamp_file) and time.time() - os.path.getmtime(timestamp_file) < 600:
        return
    if os.fork() == 0:
        backup_database("auto")
        Path(timestamp_file).touch()
        os._exit(0)

def list_backups():
    """List all backup files with metadata."""
    backups = sorted([f for f in os.listdir(DATA_DIR) if f.startswith('aio_') and f.endswith('.db') and f != 'aio.db'])
    return [(os.path.join(DATA_DIR, b), os.path.getsize(os.path.join(DATA_DIR, b)), os.path.getmtime(os.path.join(DATA_DIR, b))) for b in backups]

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
                CREATE TABLE IF NOT EXISTS apps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
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

            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompts (
                    name TEXT PRIMARY KEY,
                    content TEXT NOT NULL
                )
            """)

            # Check if prompts exist
            cursor = conn.execute("SELECT COUNT(*) FROM prompts")
            if cursor.fetchone()[0] == 0:
                # Insert default prompt once
                default_prompt = """When given a task follow the 3 steps:

Step 1: Read project and relevant files. Then ultrathink how to best solve this.
For any technical decision or problem, first ask what the most popular/deployed apps in the world do most similar to this project. Assume the best way to solve the problem already exists and your task is just to figure out how to find that and use it, not create your own method. Ask how did they solve it and how they implemented the solution? If applicable, look up the most direct source relevant docs.

Step 2: Write the changes with the following:

Write in the style I would call "library glue", where you only use library functions, no or almost no business logic, and fully rely on the library to do everything for all code lines.

Make line count as minimal as possible while doing exactly the same things, use direct library calls as often as possible, keep it readable and follow all program readability conventions, and manually run debug and inspect output and fix issues.
If rewriting existing sections of code with no features added, each change must be readable and follow all program readability conventions, run as fast or faster than previous code, be lower in line count or equal to original, use the same or greater number of direct library calls, reduce the number of states the program could be in or keep it equal, and make it simpler or keep the same complexity than before.
Specific practices:
No polling whatsoever, only event based.


Step 3:
After you make edits, run manually exactly as the user would, and check the output manually, if applicable inspect screenshots. Set an aggressive timeout on any terminal command. Don't add any features just make sure everything works and fix any issues according to library glue principles."""
                conn.execute("INSERT INTO prompts VALUES ('default', ?)", (default_prompt,))

            # Check if config exists
            cursor = conn.execute("SELECT COUNT(*) FROM config")
            if cursor.fetchone()[0] == 0:
                # Insert default config - reference the default prompt
                cursor = conn.execute("SELECT content FROM prompts WHERE name = 'default'")
                default_prompt = cursor.fetchone()[0]
                conn.execute("INSERT INTO config VALUES ('claude_prompt', ?)", (default_prompt,))
                conn.execute("INSERT INTO config VALUES ('codex_prompt', ?)", (default_prompt,))
                conn.execute("INSERT INTO config VALUES ('gemini_prompt', ?)", (default_prompt,))
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

            # Check if apps exist
            cursor = conn.execute("SELECT COUNT(*) FROM apps")
            if cursor.fetchone()[0] == 0:
                # Insert default apps
                default_apps = [
                    ("testRepo", f"cd {os.path.expanduser('~/projects/testRepoPrivate')} && $SHELL")
                ]
                for i, (name, command) in enumerate(default_apps):
                    conn.execute("INSERT INTO apps (name, command, display_order) VALUES (?, ?, ?)",
                               (name, command, i))

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

def get_prompt(name):
    """Load a prompt from database by name."""
    with WALManager(DB_PATH) as conn:
        cursor = conn.execute("SELECT content FROM prompts WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None

def load_projects():
    """Load projects from database."""
    with WALManager(DB_PATH) as conn:
        cursor = conn.execute("SELECT path FROM projects ORDER BY display_order")
        projects = [row[0] for row in cursor.fetchall()]
    return projects

def add_project(path):
    """Add a project to the database."""
    # Expand and normalize path
    path = os.path.abspath(os.path.expanduser(path))

    # Check if path exists
    if not os.path.exists(path):
        return False, f"Path does not exist: {path}"

    if not os.path.isdir(path):
        return False, f"Path is not a directory: {path}"

    with WALManager(DB_PATH) as conn:
        with conn:
            # Check if project already exists
            cursor = conn.execute("SELECT COUNT(*) FROM projects WHERE path = ?", (path,))
            if cursor.fetchone()[0] > 0:
                return False, f"Project already exists: {path}"

            # Get the next display order
            cursor = conn.execute("SELECT MAX(display_order) FROM projects")
            max_order = cursor.fetchone()[0]
            next_order = (max_order + 1) if max_order is not None else 0

            # Insert the project
            conn.execute("INSERT INTO projects (path, display_order) VALUES (?, ?)",
                        (path, next_order))

    return True, f"Added project: {path}"

def remove_project(index):
    """Remove a project from the database by index."""
    with WALManager(DB_PATH) as conn:
        with conn:
            # Get all projects
            cursor = conn.execute("SELECT id, path FROM projects ORDER BY display_order")
            projects = cursor.fetchall()

            if index < 0 or index >= len(projects):
                return False, f"Invalid project index: {index}"

            # Delete the project
            project_id, project_path = projects[index]
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

            # Reorder remaining projects
            cursor = conn.execute("SELECT id FROM projects ORDER BY display_order")
            project_ids = [row[0] for row in cursor.fetchall()]

            for i, pid in enumerate(project_ids):
                conn.execute("UPDATE projects SET display_order = ? WHERE id = ?", (i, pid))

    return True, f"Removed project: {project_path}"

def load_apps():
    """Load apps from database."""
    with WALManager(DB_PATH) as conn:
        cursor = conn.execute("SELECT name, command FROM apps ORDER BY display_order")
        apps = [(row[0], row[1]) for row in cursor.fetchall()]
    return apps

def add_app(name, command):
    """Add an app to the database."""
    if not name or not command:
        return False, "Name and command are required"

    with WALManager(DB_PATH) as conn:
        with conn:
            # Check if app already exists
            cursor = conn.execute("SELECT COUNT(*) FROM apps WHERE name = ?", (name,))
            if cursor.fetchone()[0] > 0:
                return False, f"App already exists: {name}"

            # Get the next display order
            cursor = conn.execute("SELECT MAX(display_order) FROM apps")
            max_order = cursor.fetchone()[0]
            next_order = (max_order + 1) if max_order is not None else 0

            # Insert the app
            conn.execute("INSERT INTO apps (name, command, display_order) VALUES (?, ?, ?)",
                        (name, command, next_order))

    return True, f"Added app: {name}"

def remove_app(index):
    """Remove an app from the database by index."""
    with WALManager(DB_PATH) as conn:
        with conn:
            # Get all apps
            cursor = conn.execute("SELECT id, name FROM apps ORDER BY display_order")
            apps = cursor.fetchall()

            if index < 0 or index >= len(apps):
                return False, f"Invalid app index: {index}"

            # Delete the app
            app_id, app_name = apps[index]
            conn.execute("DELETE FROM apps WHERE id = ?", (app_id,))

            # Reorder remaining apps
            cursor = conn.execute("SELECT id FROM apps ORDER BY display_order")
            app_ids = [row[0] for row in cursor.fetchall()]

            for i, aid in enumerate(app_ids):
                conn.execute("UPDATE apps SET display_order = ? WHERE id = ?", (i, aid))

    return True, f"Removed app: {app_name}"

def load_sessions(config):
    """Load sessions from database and substitute prompt values."""
    with WALManager(DB_PATH) as conn:
        cursor = conn.execute("SELECT key, name, command_template FROM sessions")
        sessions_data = cursor.fetchall()

    default_prompt = get_prompt('default')

    sessions = {}
    for key, name, cmd_template in sessions_data:
        # Check if this is a single-p session (cp, lp, gp) - these should NOT auto-execute prompts
        is_single_p = key in ['cp', 'lp', 'gp']

        # Get prompts and escape them for shell/CLI usage
        # Replace newlines with literal \n to preserve formatting while avoiding shell parsing issues
        claude_prompt = config.get('claude_prompt', default_prompt).replace('\n', '\\n').replace('"', '\\"')
        codex_prompt = config.get('codex_prompt', default_prompt).replace('\n', '\\n').replace('"', '\\"')
        gemini_prompt = config.get('gemini_prompt', default_prompt).replace('\n', '\\n').replace('"', '\\"')

        # For single-p sessions, remove prompt from command (we'll send it via tmux later)
        # For other sessions, substitute prompt placeholders normally
        if is_single_p:
            # Remove the prompt argument entirely
            cmd = cmd_template.replace(' "{CLAUDE_PROMPT}"', '').replace(' "{CODEX_PROMPT}"', '').replace(' "{GEMINI_PROMPT}"', '')
        else:
            # Substitute prompt placeholders
            cmd = cmd_template.format(
                CLAUDE_PROMPT=claude_prompt,
                CODEX_PROMPT=codex_prompt,
                GEMINI_PROMPT=gemini_prompt
            )
        sessions[key] = (name, cmd)

    return sessions

# Initialize database on first run
init_database()

# Load configuration from database
config = load_config()
DEFAULT_PROMPT = get_prompt('default')
CLAUDE_PROMPT = config.get('claude_prompt', DEFAULT_PROMPT)
CODEX_PROMPT = config.get('codex_prompt', DEFAULT_PROMPT)
GEMINI_PROMPT = config.get('gemini_prompt', DEFAULT_PROMPT)

# Get working directory, fallback to home if current dir is invalid
try:
    WORK_DIR = os.getcwd()
except FileNotFoundError:
    WORK_DIR = os.path.expanduser("~")
    os.chdir(WORK_DIR)
    print(f"⚠ Current directory was invalid, changed to: {WORK_DIR}")

WORKTREES_DIR = config.get('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees"))

PROJECTS = load_projects()
APPS = load_apps()
sessions = load_sessions(config)

def ensure_tmux_mouse_mode():
    """Ensure tmux mouse mode is enabled for better scrolling."""
    # Check if tmux server is running
    result = sp.run(['tmux', 'info'],
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    if result.returncode != 0:
        # Tmux server not running yet, will be configured when it starts
        return

    # Check current mouse mode setting
    result = sp.run(['tmux', 'show-options', '-g', 'mouse'],
                    capture_output=True, text=True)

    if result.returncode == 0:
        output = result.stdout.strip()
        # Output format: "mouse on" or "mouse off"
        if 'on' in output:
            return  # Already enabled

    # Enable mouse mode
    result = sp.run(['tmux', 'set-option', '-g', 'mouse', 'on'],
                    capture_output=True)

    if result.returncode == 0:
        print("✓ Enabled tmux mouse mode for scrolling")

# Ensure tmux mouse mode is enabled
ensure_tmux_mouse_mode()

def detect_terminal():
    """Detect available terminal emulator"""
    for term in ['ptyxis', 'gnome-terminal', 'alacritty']:
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
        print("✗ No supported terminal found (ptyxis, gnome-terminal, alacritty)")
        return False

    if terminal == 'ptyxis':
        cmd = ['ptyxis', '--', 'tmux', 'attach', '-t', session_name]
    elif terminal == 'gnome-terminal':
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
        print("✗ No supported terminal found (ptyxis, gnome-terminal, alacritty)")
        return False

    directory = os.path.expanduser(directory)
    directory = os.path.abspath(directory)

    if not os.path.exists(directory):
        print(f"✗ Directory does not exist: {directory}")
        return False

    if terminal == 'ptyxis':
        cmd = ['ptyxis', '--working-directory', directory]
    elif terminal == 'gnome-terminal':
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

def send_prompt_to_session(session_name, prompt, wait_for_completion=False, timeout=None, wait_for_ready=True, send_enter=True):
    """Send a prompt to a tmux session.

    Args:
        session_name: Name of tmux session
        prompt: Text to send to the session
        wait_for_completion: If True, wait for activity to stop before returning
        timeout: Max seconds to wait for completion (only used if wait_for_completion=True)
        wait_for_ready: If True, wait for agent to be ready before sending
        send_enter: If True, send Enter key after prompt (default True)

    Returns:
        True if successful, False otherwise

    Example:
        send_prompt_to_session('codex', 'create a test.txt file with hello world')
        send_prompt_to_session('codex', 'list files', send_enter=False)  # Insert without running
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

    # Send the prompt
    # Use -l flag to send literal keys (prevents newlines from being interpreted as Enter)
    sp.run(['tmux', 'send-keys', '-l', '-t', session_name, prompt])

    if send_enter:
        time.sleep(0.1)  # Brief delay before Enter for terminal processing
        sp.run(['tmux', 'send-keys', '-t', session_name, 'Enter'])
        print(f"✓ Sent prompt to session '{session_name}'")
    else:
        print(f"✓ Inserted prompt into session '{session_name}' (ready to edit/run)")

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

def list_jobs(running_only=False):
    """List all jobs (any directory with a session, plus worktrees) with their status.

    Args:
        running_only: If True, only show jobs that are actively running
    """
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

    # First pass: collect job info with timestamps
    jobs_with_metadata = []

    for job_path in jobs_by_path.keys():
        # Skip deleted directories
        if not os.path.exists(job_path):
            # Kill orphaned tmux sessions for deleted directories
            sessions_in_job = jobs_by_path[job_path]
            for session in sessions_in_job:
                sp.run(['tmux', 'kill-session', '-t', session],
                      capture_output=True)
            continue

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

        # Skip non-running jobs if running_only filter is enabled
        if running_only and not is_active:
            continue

        # Extract creation datetime from worktree name for sorting and display
        creation_datetime = None
        creation_display = ""
        if is_worktree:
            # Parse datetime from name like: aios-codex-20251031-185629-single
            # Format: YYYYMMDD-HHMMSS
            import re
            match = re.search(r'-(\d{8})-(\d{6})-', job_name)
            if match:
                date_str = match.group(1)  # YYYYMMDD
                time_str = match.group(2)  # HHMMSS
                try:
                    from datetime import datetime
                    creation_datetime = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")

                    # Format display
                    now = datetime.now()
                    time_diff = now - creation_datetime

                    if time_diff.total_seconds() < 60:
                        creation_display = "just now"
                    elif time_diff.total_seconds() < 3600:
                        mins = int(time_diff.total_seconds() / 60)
                        creation_display = f"{mins}m ago"
                    elif time_diff.total_seconds() < 86400:
                        hours = int(time_diff.total_seconds() / 3600)
                        creation_display = f"{hours}h ago"
                    else:
                        days = int(time_diff.total_seconds() / 86400)
                        creation_display = f"{days}d ago"
                except:
                    pass

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

        jobs_with_metadata.append({
            'path': job_path,
            'name': job_name,
            'sessions': sessions_in_job,
            'is_worktree': is_worktree,
            'is_active': is_active,
            'status_display': status_display,
            'session_info': session_info,
            'creation_datetime': creation_datetime,
            'creation_display': creation_display
        })

    # Sort: by creation datetime (oldest first, newest last)
    # Jobs without datetime (None) sort to beginning, running jobs to end
    from datetime import datetime
    jobs_with_metadata.sort(key=lambda x: x['creation_datetime'] if x['creation_datetime'] else datetime.min)

    print("Jobs:\n")

    # Display jobs in sorted order
    for job in jobs_with_metadata:
        job_path = job['path']
        job_name = job['name']
        sessions_in_job = job['sessions']
        is_worktree = job['is_worktree']
        status_display = job['status_display']
        session_info = job['session_info']
        creation_display = job['creation_display']

        # Add worktree indicator and creation time
        type_indicator = " [worktree]" if is_worktree else ""
        time_indicator = f" ({creation_display})" if creation_display else ""

        print(f"  {status_display}  {job_name}{type_indicator}{time_indicator}")
        print(f"           {session_info}")
        print(f"           {job_path}")

        # Add copy-pastable commands
        print()

        # Command to open directory in new window
        if is_worktree:
            # For worktrees, show the 'w' command if possible (using datetime sorted order)
            worktrees_list = get_worktrees_sorted_by_datetime()
            if job_name in worktrees_list:
                worktree_index = worktrees_list.index(job_name)
                print(f"           Open dir:  aio w{worktree_index}")
            else:
                print(f"           Open dir:  aio -w {job_path}")
        else:
            print(f"           Open dir:  aio -w {job_path}")

        # Command to attach to session(s)
        if sessions_in_job:
            if len(sessions_in_job) == 1:
                print(f"           Attach:    tmux attach -t {sessions_in_job[0]}")
            else:
                # Show all sessions
                for session in sessions_in_job:
                    print(f"           Attach:    tmux attach -t {session}")

        print()

def get_worktrees_sorted_by_datetime():
    """Get list of worktrees sorted by creation datetime (oldest to newest).

    Returns list of worktree names in datetime order.
    """
    if not os.path.exists(WORKTREES_DIR):
        return []

    items = [d for d in os.listdir(WORKTREES_DIR)
             if os.path.isdir(os.path.join(WORKTREES_DIR, d))]

    if not items:
        return []

    # Parse datetime from each worktree name and sort
    import re
    from datetime import datetime

    worktrees_with_datetime = []
    for item in items:
        # Parse datetime from name like: aios-codex-20251031-185629-single
        match = re.search(r'-(\d{8})-(\d{6})-', item)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            try:
                dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
                worktrees_with_datetime.append((item, dt))
            except:
                # If parsing fails, use min datetime
                worktrees_with_datetime.append((item, datetime.min))
        else:
            # Old format without datetime, sort to beginning
            worktrees_with_datetime.append((item, datetime.min))

    # Sort by datetime
    worktrees_with_datetime.sort(key=lambda x: x[1])

    # Return just the names
    return [name for name, _ in worktrees_with_datetime]

def list_worktrees():
    """List all worktrees in central directory"""
    if not os.path.exists(WORKTREES_DIR):
        print(f"No worktrees found in {WORKTREES_DIR}")
        return []

    items = get_worktrees_sorted_by_datetime()
    if not items:
        print("No worktrees found")
        return []

    print(f"Worktrees in {WORKTREES_DIR}:\n")
    for i, item in enumerate(items):
        full_path = os.path.join(WORKTREES_DIR, item)
        if os.path.isdir(full_path):
            print(f"  {i}. {item}")
    print(f"\nTo open: aio w<#>  (e.g., aio w0)")
    return items

def find_worktree(pattern):
    """Find worktree by number or name pattern"""
    if not os.path.exists(WORKTREES_DIR):
        return None

    items = get_worktrees_sorted_by_datetime()

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

    # Fallback: Get project path from worktree's .git file
    git_file = os.path.join(worktree_path, '.git')
    if os.path.isfile(git_file):
        try:
            with open(git_file, 'r') as f:
                content = f.read().strip()
                if content.startswith('gitdir: '):
                    # Extract path: gitdir: /path/to/repo/.git/worktrees/name
                    gitdir = content.replace('gitdir: ', '')
                    # Remove /.git/worktrees/name to get main repo path
                    if '/.git/worktrees/' in gitdir:
                        project_path = gitdir.split('/.git/worktrees/')[0]
                        return project_path
        except:
            pass

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

    # Check if we're currently inside the worktree being deleted
    try:
        current_dir = os.getcwd()
        # Normalize paths for comparison
        worktree_path_abs = os.path.abspath(worktree_path)
        current_dir_abs = os.path.abspath(current_dir)

        # Check if current directory is inside the worktree
        if current_dir_abs == worktree_path_abs or current_dir_abs.startswith(worktree_path_abs + os.sep):
            # Change to a safe directory before deletion
            safe_dir = project_path if os.path.exists(project_path) else os.path.expanduser("~")
            print(f"📂 Changing directory to: {safe_dir}")
            os.chdir(safe_dir)
    except FileNotFoundError:
        # Current directory already doesn't exist, change to home
        safe_dir = os.path.expanduser("~")
        os.chdir(safe_dir)
        print(f"📂 Changed to home directory (current dir was invalid)")

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
        env = get_noninteractive_git_env()
        result = sp.run(['git', '-C', project_path, 'push', 'origin', main_branch],
                        capture_output=True, text=True, env=env)

        if result.returncode == 0:
            print(f"✓ Pushed to {main_branch}")
        else:
            print(f"✗ Push failed: {result.stderr.strip()}")

    return True

# Parse args
arg = sys.argv[1] if len(sys.argv) > 1 else None
work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None
new_window = '--new-window' in sys.argv or '-w' in sys.argv
with_terminal = '--with-terminal' in sys.argv or '-t' in sys.argv

# Clean args
if new_window:
    sys.argv = [a for a in sys.argv if a not in ['--new-window', '-w']]
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None

if with_terminal:
    sys.argv = [a for a in sys.argv if a not in ['--with-terminal', '-t']]
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None
    # with_terminal implies new_window for the session
    new_window = True

# Auto-backup check (git-style: fork if needed, returns immediately)
auto_backup_check()

# Check if arg is actually a directory/number (not a session key or worktree command)
is_directory_only = new_window and arg and not arg.startswith('+') and not arg.endswith('--') and not arg.startswith('w') and arg not in sessions

# If directory-only mode, treat arg as work_dir_arg
if is_directory_only:
    work_dir_arg = arg
    arg = None

# Resolve work_dir: digit -> PROJECTS[n], path -> path, None -> WORK_DIR
# Also determine if work_dir_arg is actually a prompt (for later)
is_work_dir_a_prompt = False

if work_dir_arg and work_dir_arg.isdigit():
    idx = int(work_dir_arg)
    if 0 <= idx < len(PROJECTS):
        work_dir = PROJECTS[idx]
    elif 0 <= idx - len(PROJECTS) < len(APPS):
        # Execute app command
        app_name, app_command = APPS[idx - len(PROJECTS)]
        print(f"Running app: {app_name}")
        print(f"Command: {app_command}")
        os.system(app_command)
        sys.exit(0)
    else:
        work_dir = WORK_DIR
elif work_dir_arg and os.path.isdir(os.path.expanduser(work_dir_arg)):
    # It's a valid directory path
    work_dir = work_dir_arg
elif work_dir_arg:
    # Not a digit, not a directory - likely a prompt
    is_work_dir_a_prompt = True
    work_dir = WORK_DIR
else:
    work_dir = WORK_DIR

def get_noninteractive_git_env():
    """Get environment for non-interactive git operations (no GUI dialogs)"""
    env = os.environ.copy()

    # Keep SSH_AUTH_SOCK for SSH key authentication
    # Only remove DISPLAY to prevent GUI dialogs
    env.pop('DISPLAY', None)         # Remove X11 display (prevents GUI dialogs)
    env.pop('GPG_AGENT_INFO', None)  # Remove GPG agent that might prompt

    # Don't clear credential helpers - let them work if configured
    # This allows HTTPS credentials to work if already cached

    # Still disable terminal prompts to prevent hanging
    env['GIT_TERMINAL_PROMPT'] = '0'

    # Disable GUI askpass but allow SSH agent to work
    env['SSH_ASKPASS'] = ''  # Empty = disable SSH GUI prompts
    env['GIT_ASKPASS'] = ''  # Empty = disable Git GUI prompts

    return env

def create_worktree(project_path, session_name, check_only=False):
    """Create git worktree in central ~/projects/aiosWorktrees/

    Args:
        project_path: Path to the project
        session_name: Name for the worktree/session
        check_only: If True, only check authentication, don't create worktree

    Returns:
        If check_only=True: (auth_succeeded, error_msg)
        If check_only=False: (worktree_path, used_local_version)
    """
    if not check_only:
        os.makedirs(WORKTREES_DIR, exist_ok=True)

    project_name = os.path.basename(project_path)

    # Get current branch
    result = sp.run(['git', '-C', project_path, 'branch', '--show-current'],
                    capture_output=True, text=True)
    branch = result.stdout.strip() or 'main'

    # Fetch from GitHub to get latest server version
    if check_only:
        print(f"   Checking authentication...", end='', flush=True)
    else:
        print(f"⬇️  Fetching latest from GitHub...", end='', flush=True)

    # Use non-interactive environment to prevent GUI dialogs
    env = get_noninteractive_git_env()
    result = sp.run(['git', '-C', project_path, 'fetch', 'origin'],
                    capture_output=True, text=True, env=env)

    if result.returncode == 0:
        print(" ✓")
        if check_only:
            return (True, None)
        fetch_succeeded = True
    else:
        error_msg = result.stderr.strip()
        if 'Authentication failed' in error_msg or 'could not read Username' in error_msg or 'Permission denied' in error_msg:
            print(" ❌ FAILED")
            # Get current remote URL to provide exact fix command
            remote_result = sp.run(['git', '-C', project_path, 'remote', 'get-url', 'origin'],
                                  capture_output=True, text=True)
            fix_cmd = None
            if remote_result.returncode == 0 and 'https://github.com/' in remote_result.stdout:
                # Convert https://github.com/user/repo.git to git@github.com:user/repo.git
                https_url = remote_result.stdout.strip()
                ssh_url = https_url.replace('https://github.com/', 'git@github.com:').replace('.git\n', '.git')
                fix_cmd = f"cd {project_path} && git remote set-url origin {ssh_url}"

            if check_only:
                return (False, fix_cmd)

            # For normal operation, print error and continue with local
            print(f"\n⚠️  Authentication failed - will use LOCAL version (may be outdated!)")
            if fix_cmd:
                print(f"   Fix: {fix_cmd}")
            else:
                print(f"   Fix: Convert to SSH: git remote set-url origin git@github.com:USER/REPO.git")
            fetch_succeeded = False
        else:
            print(f"\n⚠️  Fetch warning: {error_msg}")
            if check_only:
                return (True, None)  # Non-auth errors are OK
            fetch_succeeded = True

    # If check_only, we're done
    if check_only:
        return (True, None)

    # Create worktree from either server or local version
    worktree_name = f"{project_name}-{session_name}"
    worktree_path = os.path.join(WORKTREES_DIR, worktree_name)

    if fetch_succeeded:
        print(f"🌱 Creating worktree from origin/{branch}...", end='', flush=True)
        source = f"origin/{branch}"
    else:
        print(f"⚠️  Creating worktree from LOCAL {branch} (NOT synced with server!)...", end='', flush=True)
        source = branch  # Use local branch instead of origin/branch

    result = sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', f"wt-{worktree_name}", worktree_path, source],
                    capture_output=True, text=True)

    if result.returncode == 0:
        print(" ✓")
        # Return tuple: (worktree_path, used_local_version)
        return (worktree_path, not fetch_succeeded)
    else:
        print(f"\n✗ Failed to create worktree: {result.stderr.strip()}")
        return (None, False)

def parse_agent_specs_and_prompt(argv, start_idx):
    """Parse agent specifications and prompt from command line arguments.

    Returns: (agent_specs, prompt, using_default_protocol)
        agent_specs: list of (agent_key, count) tuples
        prompt: the final prompt string
        using_default_protocol: bool indicating if default prompt was used
    """
    agent_specs, prompt_parts, parsing_agents = [], [], True

    for arg_part in argv[start_idx:]:
        if arg_part in ['--seq', '--sequential']:
            continue

        if parsing_agents and ':' in arg_part and len(arg_part) <= 4:
            parts = arg_part.split(':')
            if len(parts) == 2 and parts[0] in ['c', 'l', 'g'] and parts[1].isdigit():
                agent_specs.append((parts[0], int(parts[1])))
                continue

        parsing_agents = False
        prompt_parts.append(arg_part)

    return (agent_specs, CODEX_PROMPT, True) if not prompt_parts else (agent_specs, ' '.join(prompt_parts), False)

# Handle project number shortcut: aio 1, aio 2, etc.
if arg and arg.isdigit() and not work_dir_arg:
    idx = int(arg)
    if 0 <= idx < len(PROJECTS):
        project_path = PROJECTS[idx]
        print(f"📂 Opening project {idx}: {project_path}")
        os.chdir(project_path)
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    elif 0 <= idx - len(PROJECTS) < len(APPS):
        # Execute app command
        app_name, app_command = APPS[idx - len(PROJECTS)]

        # Extract directory for cleaner display
        if app_command.startswith('cd ') and ' && ' in app_command:
            parts = app_command.split(' && ', 1)
            dir_path = parts[0].replace('cd ', '').strip()
            # Simplify home directory path
            if dir_path.startswith(os.path.expanduser('~')):
                dir_path = dir_path.replace(os.path.expanduser('~'), '~')
            print(f"▶️  {app_name} → {dir_path}")
        else:
            print(f"▶️  {app_name}")

        os.system(app_command)
        sys.exit(0)
    else:
        print(f"✗ Invalid index: {idx}")
        print(f"   Valid range: 0-{len(PROJECTS) + len(APPS) - 1}")
        print(f"   Projects: 0-{len(PROJECTS)-1}, Apps: {len(PROJECTS)}-{len(PROJECTS) + len(APPS) - 1}")
        sys.exit(1)


# Handle worktree commands (but not 'watch')
if arg and arg.startswith('w') and arg != 'watch':
    if arg == 'w':
        # List worktrees
        list_worktrees()
        sys.exit(0)
    elif len(arg) > 1:
        # Check if it's a removal command (ends with - or --)
        if arg.endswith('--'):
            # Remove and push: w0--, w1--, etc.
            pattern = arg[1:-2]  # Extract pattern between 'w' and '--'
            commit_msg = work_dir_arg  # First arg after command is commit message
            skip_confirm = '--yes' in sys.argv or '-y' in sys.argv

            if not pattern:
                print("✗ Usage: ./aio.py w<#/name>-- [commit message] [--yes/-y]")
                sys.exit(1)

            worktree_path = find_worktree(pattern)
            if worktree_path:
                remove_worktree(worktree_path, push=True, commit_msg=commit_msg, skip_confirm=skip_confirm)
            else:
                print(f"✗ Worktree not found: {pattern}")
            sys.exit(0)
        elif arg.endswith('-'):
            # Remove only: w0-, w1-, etc.
            pattern = arg[1:-1]  # Extract pattern between 'w' and '-'
            skip_confirm = '--yes' in sys.argv or '-y' in sys.argv

            if not pattern:
                print("✗ Usage: ./aio.py w<#/name>- [--yes/-y]")
                sys.exit(1)

            worktree_path = find_worktree(pattern)
            if worktree_path:
                remove_worktree(worktree_path, push=False, skip_confirm=skip_confirm)
            else:
                print(f"✗ Worktree not found: {pattern}")
            sys.exit(0)
        else:
            # Open worktree: w0, w1, etc.
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
    # Check if there are worktrees needing review
    review_count = 0
    if os.path.exists(WORKTREES_DIR):
        worktrees = get_worktrees_sorted_by_datetime()
        for wt_name in worktrees:
            wt_path = os.path.join(WORKTREES_DIR, wt_name)
            session = get_session_for_worktree(wt_path)
            if not session or not is_pane_receiving_output(session):
                review_count += 1

    review_notice = ""
    if review_count > 0:
        review_notice = f"\n💡 You have {review_count} worktrees ready for review! Run: aio review\n"

    print(f"""aio - AI agent session manager{review_notice}
QUICK START:
  aio c               Start codex in current directory
  aio cp              Start codex with prompt (can edit before running)
  aio cpp             Start codex with prompt (auto-execute)
  aio c++             Start codex in new worktree (current dir)
  aio c++ 0           Start codex in new worktree (project 0)
MULTI-AGENT (run N agents in parallel worktrees):
  aio multi c:3                 Launch 3 codex (DEFAULT: 11-step protocol)
  aio multi c:3 "task"          Launch 3 codex with custom task
  aio multi c:2 l:1             Mixed agents (DEFAULT: 11-step protocol)
  aio multi c:3 --seq           Sequential (DEFAULT: 11-step protocol)
  aio multi 0 c:2 "task"        Or use project #: launch in project 0
PORTFOLIO (run agents across ALL saved projects):
  aio all c:2                   2 codex per project (DEFAULT: 11-step protocol - overnight!)
  aio all c:2 "task"            2 codex per project with custom task
  aio all c:1 l:1               Mixed agents across all (DEFAULT protocol)
  aio all c:2 --seq             Sequential across projects (DEFAULT protocol)
SESSIONS: c=codex  l=claude  g=gemini  h=htop  t=top
  aio <key>           Attach to session (or create if needed)
  aio <key> <#>       Start in saved project # (0-{len(PROJECTS)-1})
  aio <key> -w        Launch in new window
  aio <key> -t        Launch session + separate terminal
PROMPTS:
  aio cp/lp/gp        Insert prompt (ready to edit before running)
  aio cpp/lpp/gpp     Auto-run prompt immediately
WORKTREES:
  aio <key>++         New worktree in current dir
  aio <key>++ <#>     New worktree in project #
  aio w               List all worktrees
  aio w<#>            Open worktree #
  aio w<#>-           Remove worktree (no push)
  aio w<#>--          Remove worktree and push to main
MANAGEMENT:
  aio jobs            Show all active work with status
  aio jobs --running  Show only running jobs (filter out review)
  aio review          Review & clean up finished worktrees (NEW!)
  aio cleanup         Delete all worktrees (with confirmation)
  aio cleanup --yes   Delete all worktrees (skip confirmation)
  aio ls              List all tmux sessions
  aio p               Show saved projects
DATABASE:
  aio backups         List all database backups
  aio restore <file>  Restore database from backup
GIT:
  aio setup <url>     Initialize git repo with remote
  aio push ["msg"]    Quick commit and push
  aio pull            Replace local with server (destructive)
  aio revert [N]      Undo last N commits (default: 1)
SETUP:
  aio install         Install as global 'aio' command
  aio add [path]      Add project to saved list
  aio remove <#>      Remove project from list
Working directory: {WORK_DIR}
Run 'aio help' for detailed documentation""")
    if PROJECTS or APPS:
        print(f"Saved projects & apps (use 'aio <#>' or 'aio -w <#>'):")
        for i, proj in enumerate(PROJECTS):
            exists = "✓" if os.path.exists(proj) else "✗"
            print(f"  {i}. {exists} {proj}")
        for i, (app_name, app_cmd) in enumerate(APPS):
            # Extract directory from cd commands for cleaner display
            if app_cmd.startswith('cd ') and ' && ' in app_cmd:
                parts = app_cmd.split(' && ', 1)
                dir_path = parts[0].replace('cd ', '').strip()
                # Simplify home directory path
                if dir_path.startswith(os.path.expanduser('~')):
                    dir_path = dir_path.replace(os.path.expanduser('~'), '~')
                print(f"  {len(PROJECTS) + i}. {app_name} → {dir_path}")
            else:
                # For non-cd commands, just show the app name and a simplified command
                cmd_display = app_cmd if len(app_cmd) <= 50 else app_cmd[:47] + "..."
                print(f"  {len(PROJECTS) + i}. {app_name} → {cmd_display}")
elif arg == 'help' or arg == '--help' or arg == '-h':
    print(f"""aio - AI agent session manager (DETAILED HELP)
═══════════════════════════════════════════════════════════════════════════════
SESSION MANAGEMENT
═══════════════════════════════════════════════════════════════════════════════
Sessions: c=codex  l=claude  g=gemini  h=htop  t=top
BASIC:
  aio <key>              Attach to session (create if needed)
  aio <key> <#>          Start in saved project # (0-{len(PROJECTS)-1})
  aio <key> <dir>        Start in custom directory
  aio +<key>             Create NEW timestamped instance
  aio <key> -w           Launch in new window
  aio <key> -t           Launch session + separate terminal
PROMPTS (insert vs auto-run):
  aio cp/lp/gp           Insert default prompt (can edit before running)
  aio cpp/lpp/gpp        Auto-execute default prompt immediately
  aio <key> "custom"     Start and send custom prompt
WORKTREES (isolated git branches):
  aio <key>--            New worktree in current directory
  aio <key>-- <#>        New worktree in saved project #
  aio <key>-- -t         New worktree + terminal window
═══════════════════════════════════════════════════════════════════════════════
WORKTREE MANAGEMENT
═══════════════════════════════════════════════════════════════════════════════
  aio w                  List all worktrees
  aio w<#/name>          Open worktree by index or name
  aio w<#> -w            Open worktree in new window
  aio w<#/name>-         Remove worktree (no git push)
  aio w<#>- -y           Remove without confirmation
  aio w<#/name>--        Remove, merge to main, and push
  aio w<#>-- --yes       Remove and push (skip confirmation)
  aio w<#>-- "message"   Remove and push with custom commit message
═══════════════════════════════════════════════════════════════════════════════
PROJECT & APP MANAGEMENT
═══════════════════════════════════════════════════════════════════════════════
  aio p                  List all saved projects & apps (unified numbering)
  aio <#>                Open project # or run app # (e.g., aio 0, aio 10)
  aio -w <#>             Open project # in new window
  aio add [path]         Add project (defaults to current dir)
  aio add-app <name> <command>  Add executable app
  aio remove <#>         Remove project from saved list
  aio remove-app <#>     Remove app from saved list
Note: Projects (0-9) = directories to cd into. Apps (10+) = commands to execute.
═══════════════════════════════════════════════════════════════════════════════
MONITORING & AUTOMATION
═══════════════════════════════════════════════════════════════════════════════
  aio jobs               Show all active work with status
  aio jobs --running     Show only running jobs (filter out review)
  aio jobs -r            Same as --running (short form)
  aio review             Review & clean up finished worktrees 🆕
                        - Opens each worktree in tmux (Ctrl+B D to detach)
                        - Quick inspect: l=ls g=git d=diff h=log
                        - Actions: 1=push+delete 2=delete 3=keep 4=stop
                        - Terminal-first workflow (no GUI needed)
  aio cleanup            Delete all worktrees (with confirmation)
  aio cleanup --yes      Delete all worktrees (skip confirmation)
  aio ls                 List all tmux sessions
  aio watch <session>    Auto-respond to prompts (watch once)
  aio watch <session> 60 Auto-respond for 60 seconds
  aio send <sess> "text" Send prompt to existing session
  aio send <sess> "text" --wait  Send and wait for completion
MULTI-AGENT PARALLEL:
  aio multi <#> c:3 g:1 "prompt"  Run 3 codex + 1 gemini in parallel
  aio multi <#> c:2 l:1 "prompt"  Run 2 codex + 1 claude in parallel
═══════════════════════════════════════════════════════════════════════════════
GIT OPERATIONS
═══════════════════════════════════════════════════════════════════════════════
  aio setup <url>        Initialize repo and add remote
  aio push               Quick commit and push (default message)
  aio push "message"     Commit and push with custom message
  aio push -y            Push without confirmation (in worktrees)
  aio pull               Replace local with server (destructive, needs confirmation)
  aio pull -y            Pull without confirmation
  aio revert             Undo last commit
  aio revert 3           Undo last 3 commits
Note: Works in any git directory, not just worktrees
═══════════════════════════════════════════════════════════════════════════════
SETUP & CONFIGURATION
═══════════════════════════════════════════════════════════════════════════════
  aio install            Install as global 'aio' command
  aio x                  Kill all tmux sessions
FLAGS:
  -w, --new-window       Launch in new terminal window
  -t, --with-terminal    Launch session + separate terminal
  -y, --yes              Skip confirmation prompts
TERMINALS: Auto-detects ptyxis, gnome-terminal, alacritty
DATABASE: ~/.local/share/aios/aio.db
WORKTREES: {WORKTREES_DIR}
═══════════════════════════════════════════════════════════════════════════════
DATABASE BACKUP & RESTORE
═══════════════════════════════════════════════════════════════════════════════
  aio backups            List all database backups with timestamps
  aio restore <file>     Restore database from backup (with confirmation)
AUTOMATIC BACKUPS:
• Backups created automatically every 10 minutes (silent, zero delay)
• Uses git-style fork: parent continues instantly, child backs up in background
• Backups stored in: ~/.local/share/aios/aio_auto_YYYYMMDD_HHMMSS.db
• Protects: projects, sessions, prompts, configuration, worktree history
MANUAL BACKUP:
• Create manual backup: Use backup_database("label") in Python
• Restore from backup: aio restore <filename>
• Backups use SQLite's .backup() method (safe, atomic, consistent)
═══════════════════════════════════════════════════════════════════════════════
EXAMPLES
═══════════════════════════════════════════════════════════════════════════════
Getting Started:
  aio install              Make 'aio' globally available
  aio c                    Start codex in current directory
  aio cp                   Start codex with editable prompt
  aio cpp                  Start codex with auto-run prompt
Sessions:
  aio c 0                  Start codex in project 0
  aio l -w                 Start claude in new window
  aio g 2 -t               Start gemini in project 2 + terminal
Worktrees:
  aio c++                  Codex in new worktree (current dir)
  aio c++ 0 -t             Codex in new worktree (project 0) + terminal
  aio l++ -w               Claude in new worktree in new window
Management:
  aio jobs                 View all active work
  aio review               Review finished worktrees one-by-one
  aio w                    List worktrees
  aio w0 -w                Open worktree 0 in new window
  aio w0-- "Done"          Remove worktree 0 and push to main
Automation:
  aio send codex "fix bug" Send prompt to running session
  aio multi 0 c:3 "task"   Run 3 codex in parallel on task
  aio push "Fix login"     Quick commit and push
═══════════════════════════════════════════════════════════════════════════════
NOTES:
• Auto-updates from git on each run (always latest version)
• Auto-backup every 10 minutes (silent, zero delay, stored in ~/.local/share/aios)
• Works in any git directory for push/worktree commands
• Mouse mode enabled: Hold Shift to select and copy text
• Database stores: projects, sessions, prompts, configuration
Working directory: {WORK_DIR}
Saved projects & apps (examples: 'aio 0' opens project 0, 'aio 10' runs first app):""")
    for i, proj in enumerate(PROJECTS):
        exists = "✓" if os.path.exists(proj) else "✗"
        print(f"  {i}. {exists} {proj}")
    for i, (app_name, app_cmd) in enumerate(APPS):
        # Extract directory from cd commands for cleaner display
        if app_cmd.startswith('cd ') and ' && ' in app_cmd:
            parts = app_cmd.split(' && ', 1)
            dir_path = parts[0].replace('cd ', '').strip()
            # Simplify home directory path
            if dir_path.startswith(os.path.expanduser('~')):
                dir_path = dir_path.replace(os.path.expanduser('~'), '~')
            print(f"  {len(PROJECTS) + i}. {app_name} → {dir_path}")
        else:
            # For non-cd commands, just show the app name and a simplified command
            cmd_display = app_cmd if len(app_cmd) <= 50 else app_cmd[:47] + "..."
            print(f"  {len(PROJECTS) + i}. {app_name} → {cmd_display}")
elif arg == 'install':
    # Install aio as a global command
    bin_dir = os.path.expanduser("~/.local/bin")
    aio_link = os.path.join(bin_dir, "aio")
    script_path = os.path.abspath(__file__)

    # Create bin directory if needed
    os.makedirs(bin_dir, exist_ok=True)

    # Remove existing symlink if present
    if os.path.exists(aio_link):
        if os.path.islink(aio_link):
            os.remove(aio_link)
            print(f"✓ Removed existing symlink: {aio_link}")
        else:
            print(f"✗ {aio_link} exists but is not a symlink. Please remove it manually.")
            sys.exit(1)

    # Create symlink
    os.symlink(script_path, aio_link)
    print(f"✓ Created symlink: {aio_link} -> {script_path}")

    # Check if ~/.local/bin is in PATH
    user_path = os.environ.get('PATH', '')
    if bin_dir not in user_path:
        print(f"\n⚠ Warning: {bin_dir} is not in your PATH")
        print(f"Add this line to your ~/.bashrc or ~/.zshrc:")
        print(f'  export PATH="$HOME/.local/bin:$PATH"')
        print(f"\nThen run: source ~/.bashrc (or restart your terminal)")
    else:
        print(f"\n✓ {bin_dir} is in your PATH")
        print(f"✓ You can now run 'aio' from anywhere!")

    print(f"\nThe script will auto-update from git on each run.")
elif arg == 'backups' or arg == 'backup':
    backups = list_backups()
    if not backups:
        print("No backups found.")
    else:
        print(f"\n📦 Database Backups ({len(backups)} total)")
        print("━" * 70)
        for i, (path, size, mtime) in enumerate(backups[-10:], 1):
            name = os.path.basename(path)
            age = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{i:2}. {name}")
            print(f"    {size:,} bytes | {age}")
        print(f"\n📁 Location: {DATA_DIR}")
        print(f"   Restore: aio restore <filename>")
elif arg == 'restore':
    if not work_dir_arg:
        print("Usage: aio restore <backup_filename>")
        backups = list_backups()
        if backups:
            print(f"\nAvailable backups:")
            for i, (path, size, mtime) in enumerate(backups[-5:], 1):
                print(f"  {os.path.basename(path)}")
        sys.exit(1)
    backup_path = os.path.join(DATA_DIR, work_dir_arg) if not os.path.isabs(work_dir_arg) else work_dir_arg
    if not os.path.exists(backup_path):
        print(f"✗ Backup not found: {backup_path}")
        sys.exit(1)
    print(f"⚠️  WARNING: This will overwrite current database!")
    print(f"   Restoring from: {os.path.basename(backup_path)}")
    response = input("   Continue? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    restore_database(backup_path)
    print(f"✅ Database restored successfully!")
elif arg == 'watch':
    # Watch a tmux session and auto-respond to patterns
    if not work_dir_arg:
        print("✗ Usage: aio watch <session_name> [duration_seconds]")
        print("\nExamples:")
        print("  aio watch codex          # Watch codex session, respond once and exit")
        print("  aio watch codex 60       # Watch codex session for 60 seconds")
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
        print("✗ Usage: aio send <session_name> <prompt>")
        print("\nExamples:")
        print("  aio send codex 'create a test file'")
        print("  aio send claude-aios 'explain this code'")
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
    # Usage: aio multi c:3 "prompt" (current dir) OR aio multi <project#> c:3 "prompt"

    # Check if first arg is a project number or agent spec
    if work_dir_arg and work_dir_arg.isdigit():
        # Explicit project number provided: aio multi 3 c:2 "task"
        project_idx = int(work_dir_arg)
        if not (0 <= project_idx < len(PROJECTS)):
            print(f"✗ Invalid project index: {project_idx}")
            sys.exit(1)
        project_path = PROJECTS[project_idx]
        start_parse_at = 3  # Start parsing from argv[3]
    else:
        # No project number, use current directory: aio multi c:2 "task"
        project_path = os.getcwd()
        start_parse_at = 2  # Start parsing from argv[2]

    # Check for sequential flag
    sequential = '--seq' in sys.argv or '--sequential' in sys.argv

    # Parse agent specifications and prompt using helper function
    agent_specs, prompt, using_default_protocol = parse_agent_specs_and_prompt(sys.argv, start_parse_at)

    if not agent_specs:
        print("✗ No agent specifications provided")
        sys.exit(1)

    # Calculate total instances
    total_instances = sum(count for _, count in agent_specs)

    mode = "sequentially (one by one)" if sequential else "in parallel (all at once)"
    print(f"🚀 Starting {total_instances} agent instances {mode}...")
    print(f"   Project: {project_path}")
    print(f"   Agents: {', '.join(f'{key}×{count}' for key, count in agent_specs)}")
    if using_default_protocol:
        print(f"   Task: 🔬 DEFAULT - Execute 11-step optimization protocol")
        print(f"         (Ultrathink → Run → Find pain → Research → Simplify → Rewrite → Debug → Delete → Optimize → Debug → Report)")
    else:
        print(f"   Prompt: {prompt}")
    if sequential:
        print(f"   Mode: Sequential - each agent completes before next starts")
    print()

    # Create worktrees and launch sessions
    launched_sessions = []

    # Escape prompt for shell usage using stdlib
    escaped_prompt = shlex.quote(prompt)

    for agent_key, count in agent_specs:
        base_name, base_cmd = sessions.get(agent_key, (None, None))

        if not base_name:
            print(f"✗ Unknown agent key: {agent_key}")
            continue

        for instance_num in range(count):
            # Create unique worktree name with full date and command source
            import time
            date_str = datetime.now().strftime('%Y%m%d')
            time_str = datetime.now().strftime('%H%M%S')
            time.sleep(0.01)  # Ensure unique timestamps
            worktree_name = f"{base_name}-{date_str}-{time_str}-multi-{instance_num}"

            # Create worktree
            worktree_result = create_worktree(project_path, worktree_name)
            worktree_path = worktree_result[0] if worktree_result else None

            if not worktree_path:
                print(f"✗ Failed to create worktree for {base_name} instance {instance_num+1}")
                continue

            # Construct full command with prompt baked in (like lpp/gpp/cpp)
            full_cmd = f'{base_cmd} "{escaped_prompt}"'

            # Create tmux session in worktree with prompt already included
            # IMPORTANT: Use clean environment to prevent GUI dialogs in the agent session
            session_name = worktree_name
            env = get_noninteractive_git_env()
            sp.run(['tmux', 'new', '-d', '-s', session_name, '-c', worktree_path, full_cmd],
                  capture_output=True, env=env)

            launched_sessions.append((session_name, base_name, instance_num+1, worktree_path))
            print(f"✓ Created {base_name} instance {instance_num+1}: {session_name}")

    if not launched_sessions:
        print("✗ No sessions were created")
        sys.exit(1)

    # No need to send prompts separately - they're already baked into the commands
    print(f"\n✓ All {len(launched_sessions)} agents launched with prompts!")

    mode_msg = "one by one" if sequential else "in parallel"
    print(f"\n✓ All {len(launched_sessions)} agents launched {mode_msg}!")
    print(f"\n📊 Monitor all agents:")
    print(f"   aio jobs")
    print(f"\n📂 Open worktree directory:")
    for session_name, agent_name, instance_num, worktree_path in launched_sessions:
        print(f"   aio -w {worktree_path}  # {agent_name} #{instance_num}")
    print(f"\n🔗 Attach to specific agent:")
    for session_name, agent_name, instance_num, worktree_path in launched_sessions:
        print(f"   tmux attach -t {session_name}  # {agent_name} #{instance_num}")
elif arg == 'all':
    # Run agents across ALL saved projects (portfolio-level operation)
    # Usage: aio all c:2 "prompt" (parallel) OR aio all c:2 --seq "prompt" (sequential)

    # Check for sequential flag
    sequential = '--seq' in sys.argv or '--sequential' in sys.argv

    # Parse agent specifications and prompt using helper function
    agent_specs, prompt, using_default_protocol = parse_agent_specs_and_prompt(sys.argv, 2)

    if not agent_specs:
        print("✗ No agent specifications provided")
        print("\nUsage: aio all <agent_specs>... <prompt>")
        print("\nExamples:")
        print("  aio all c:2 'find all bugs'           # 2 codex per project (parallel)")
        print("  aio all c:1 l:1 'optimize'            # Mixed agents per project")
        print("  aio all c:2 --seq 'run tests'         # Sequential (one project at a time)")
        print("\nAgent specs:")
        print("  c:N  - N codex instances per project")
        print("  l:N  - N claude instances per project")
        print("  g:N  - N gemini instances per project")
        sys.exit(1)

    # Calculate total instances across all projects
    agents_per_project = sum(count for _, count in agent_specs)
    total_projects = len(PROJECTS)
    total_agents = agents_per_project * total_projects

    mode = "sequentially (one project at a time)" if sequential else "in parallel (all at once)"
    print(f"🌍 Portfolio Operation: {total_agents} agents across {total_projects} projects {mode}")
    print(f"   Agents per project: {', '.join(f'{key}×{count}' for key, count in agent_specs)}")
    if using_default_protocol:
        print(f"   Task: 🔬 DEFAULT - Execute 11-step optimization protocol")
        print(f"         (Ultrathink → Run → Find pain → Research → Simplify → Rewrite → Debug → Delete → Optimize → Debug → Report)")
    else:
        print(f"   Prompt: {prompt}")
    if sequential:
        print(f"   Mode: Sequential - complete each project before starting next")
    print()

    # STEP 1: Check authentication for ALL projects first
    print("🔐 Checking authentication for all projects...")
    print("=" * 80)

    auth_failures = []  # List of (project_idx, project_name, project_path, fix_cmd)

    for project_idx, project_path in enumerate(PROJECTS):
        project_name = os.path.basename(project_path)
        print(f"Project {project_idx}: {project_name:<30}", end='')

        # Check if project exists
        if not os.path.exists(project_path):
            print("⚠️  SKIPPED (does not exist)")
            continue

        # Check if it's a git repository
        result = sp.run(['git', '-C', project_path, 'rev-parse', '--git-dir'],
                       capture_output=True)
        if result.returncode != 0:
            print("⚠️  SKIPPED (not a git repository)")
            continue

        # Check authentication
        auth_ok, fix_cmd = create_worktree(project_path, "", check_only=True)

        if not auth_ok:
            auth_failures.append((project_idx, project_name, project_path, fix_cmd))

    # If any authentication failures, stop and show how to fix
    if auth_failures:
        print("\n" + "=" * 80)
        print("❌ AUTHENTICATION FAILED for the following projects:")
        print("=" * 80)

        for idx, name, path, fix_cmd in auth_failures:
            print(f"\nProject {idx}: {name}")
            print(f"Path: {path}")
            if fix_cmd:
                print(f"Fix:  {fix_cmd}")
            else:
                print(f"Fix:  cd {path} && git remote set-url origin git@github.com:USER/REPO.git")

        print("\n" + "=" * 80)
        print("🔧 TO FIX ALL AT ONCE, run these commands:")
        print("-" * 80)
        for idx, name, path, fix_cmd in auth_failures:
            if fix_cmd:
                print(fix_cmd)
            else:
                print(f"cd {path} && git remote set-url origin git@github.com:USER/REPO.git")

        print("\n" + "=" * 80)
        print("ℹ️  WHY SSH IS BETTER:")
        print("   • No password prompts")
        print("   • Works with aio's no-dialog approach")
        print("   • More secure than storing passwords")
        print("\n✅ After fixing, run 'aio all' again and all projects will work!")
        sys.exit(1)

    print("\n✅ All projects authenticated successfully!")
    print()

    # Track all launched sessions across all projects
    all_launched_sessions = []
    project_results = []
    projects_using_local = []  # Track projects that couldn't fetch latest

    # Escape prompt for shell usage using stdlib
    escaped_prompt = shlex.quote(prompt)

    # STEP 2: Now create worktrees and launch agents
    for project_idx, project_path in enumerate(PROJECTS):
        project_name = os.path.basename(project_path)
        print(f"\n{'='*80}")
        print(f"📁 Project {project_idx}: {project_name}")
        print(f"   Path: {project_path}")
        print(f"{'='*80}")

        # Check if project exists
        if not os.path.exists(project_path):
            print(f"⚠️  Project does not exist, skipping...")
            project_results.append((project_idx, project_name, "SKIPPED", []))
            continue

        # Create worktrees and launch sessions for this project
        project_sessions = []

        for agent_key, count in agent_specs:
            base_name, base_cmd = sessions.get(agent_key, (None, None))

            if not base_name:
                print(f"✗ Unknown agent key: {agent_key}")
                continue

            for instance_num in range(count):
                # Create unique worktree name with full date and command source
                import time
                date_str = datetime.now().strftime('%Y%m%d')
                time_str = datetime.now().strftime('%H%M%S')
                time.sleep(0.01)  # Ensure unique timestamps
                worktree_name = f"{base_name}-{date_str}-{time_str}-all-{instance_num}"

                # Create worktree
                worktree_result = create_worktree(project_path, worktree_name)
                worktree_path = worktree_result[0] if worktree_result else None
                used_local = worktree_result[1] if worktree_result else False

                if not worktree_path:
                    print(f"✗ Failed to create worktree for {base_name} instance {instance_num+1}")
                    continue

                # Track if this project is using local code
                if used_local and project_name not in projects_using_local:
                    projects_using_local.append(project_name)

                # Construct full command with prompt baked in (like lpp/gpp/cpp)
                full_cmd = f'{base_cmd} "{escaped_prompt}"'

                # Create tmux session in worktree with prompt already included
                # IMPORTANT: Use clean environment to prevent GUI dialogs in the agent session
                session_name = worktree_name
                env = get_noninteractive_git_env()
                sp.run(['tmux', 'new', '-d', '-s', session_name, '-c', worktree_path, full_cmd],
                      capture_output=True, env=env)

                project_sessions.append((session_name, base_name, instance_num+1, project_name, worktree_path))
                print(f"✓ Created {base_name} instance {instance_num+1}: {session_name}")

        if not project_sessions:
            print(f"✗ No sessions created for this project")
            project_results.append((project_idx, project_name, "FAILED", []))
            continue

        # No need to send prompts separately - they're already baked into the commands
        print(f"\n✓ Launched {len(project_sessions)} agents for {project_name} with prompts!")

        all_launched_sessions.extend(project_sessions)
        project_results.append((project_idx, project_name, "LAUNCHED", project_sessions))

        if sequential:
            print(f"\n✓ Completed project {project_idx}: {project_name}")
        else:
            print(f"\n✓ Launched agents for project {project_idx}: {project_name}")

    # Summary
    print(f"\n{'='*80}")
    print(f"🎯 PORTFOLIO OPERATION SUMMARY")
    print(f"{'='*80}")
    print(f"Total agents launched: {len(all_launched_sessions)}")
    print(f"Projects processed: {len([r for r in project_results if r[2] == 'LAUNCHED'])}/{total_projects}")

    print(f"\n📊 Monitor all agents:")
    print(f"   aio jobs")

    print(f"\n📁 Projects and their agents:")
    for proj_idx, proj_name, status, sessions in project_results:
        if status == "LAUNCHED":
            print(f"\n   Project {proj_idx}: {proj_name} ({len(sessions)} agents)")
            print(f"   📂 Open directories:")
            for session_name, agent_name, instance_num, _, worktree_path in sessions:
                print(f"      aio -w {worktree_path}  # {agent_name} #{instance_num}")
            print(f"   🔗 Attach to agents:")
            for session_name, agent_name, instance_num, _, worktree_path in sessions:
                print(f"      tmux attach -t {session_name}  # {agent_name} #{instance_num}")
        elif status == "SKIPPED":
            print(f"\n   Project {proj_idx}: {proj_name} (SKIPPED - does not exist)")
        elif status == "FAILED":
            print(f"\n   Project {proj_idx}: {proj_name} (FAILED - no agents created)")

    mode_msg = "sequentially" if sequential else "in parallel"
    print(f"\n✓ Portfolio operation complete! All agents launched {mode_msg}.")
    if not sequential:
        print(f"💤 Good time to sleep/step away! Agents working overnight.")
elif arg == 'jobs':
    # Check for --running flag
    running_only = '--running' in sys.argv or '-r' in sys.argv
    list_jobs(running_only=running_only)
elif arg == 'review':
    # Review mode for worktrees
    import time
    import re
    from datetime import datetime

    # Get worktrees needing review
    if not os.path.exists(WORKTREES_DIR):
        print("No worktrees directory found")
        sys.exit(0)

    worktrees = get_worktrees_sorted_by_datetime()
    review_worktrees = []

    for wt_name in worktrees:
        wt_path = os.path.join(WORKTREES_DIR, wt_name)
        session = get_session_for_worktree(wt_path)

        # Include if no session or session is inactive
        if not session or not is_pane_receiving_output(session):
            review_worktrees.append((wt_name, wt_path))

    if not review_worktrees:
        print("✓ No worktrees need review!")
        sys.exit(0)

    # Start screen
    print(f"\n📋 REVIEW MODE - {len(review_worktrees)} worktrees need review")
    print("=" * 60)
    print("\n📖 Instructions:")
    print("  1. Opens agent session if available (codex/claude/gemini output)")
    print("  2. Review agent's work, then detach: Ctrl+B then D")
    print("  3. Inspect files: l=ls g=git d=diff h=log t=terminal v=vscode")
    print("  4. Take action: 1=push+delete 2=delete 3=keep 4=stop")
    print("\n💡 TIP: Hold Shift to select text in tmux")
    print("=" * 60)
    input("\nPress Enter to start review... ")

    for idx, (wt_name, wt_path) in enumerate(review_worktrees):
        print(f"\n[{idx+1}/{len(review_worktrees)}] {wt_name}")

        # Show age if available
        match = re.search(r'-(\d{8})-(\d{6})-', wt_name)
        if match:
            try:
                created = datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S")
                age = datetime.now() - created
                print(f"Age: {age.days}d {age.seconds//3600}h")
            except:
                pass

        # Check for agent session first (session name = worktree name)
        agent_session_exists = sp.run(['tmux', 'has-session', '-t', wt_name],
                                      capture_output=True).returncode == 0
        session_to_attach = None

        if agent_session_exists:
            # Agent session exists - attach to see agent's work
            print(f"🤖 Found agent session: {wt_name}")
            print(f"💡 Review agent output, then detach: Ctrl+B D")
            session_to_attach = wt_name
        else:
            # No agent session - create review session for browsing
            print(f"📁 No agent session, creating file browser")
            print(f"💡 Browse files, then detach: Ctrl+B D")
            session_to_attach = f"review-{idx}"

            # Kill any old review session
            sp.run(['tmux', 'kill-session', '-t', session_to_attach],
                   stdout=sp.DEVNULL, stderr=sp.DEVNULL)

            # Create new session in worktree directory
            if sp.run(['tmux', 'new-session', '-d', '-s', session_to_attach, '-c', wt_path],
                      capture_output=True).returncode != 0:
                print(f"✗ Failed to create session")
                continue

        # Attach to session (blocks until detach)
        print(f"Opening: {wt_path}\n")
        sp.run(['tmux', 'attach-session', '-t', session_to_attach])

        # Review options
        print(f"\n📁 Inspect: l=ls  g=git-status  d=diff  h=log  t=terminal  v=vscode")
        print(f"🎯 Action: 1=push+del  2=delete  3=keep  4=stop")

        while True:
            action = input("Choice: ").strip().lower()

            # Inspection commands
            if action == 'l':
                result = sp.run(['ls', '-la', wt_path], capture_output=True, text=True)
                print(result.stdout[:500])  # First 500 chars
                continue
            elif action == 'g':
                result = sp.run(['git', '-C', wt_path, 'status', '--short'],
                               capture_output=True, text=True)
                print(result.stdout or "Clean")
                continue
            elif action == 'd':
                result = sp.run(['git', '-C', wt_path, 'diff', 'HEAD~1', '--stat'],
                               capture_output=True, text=True)
                print(result.stdout[:500] or "No diff")
                continue
            elif action == 'h':
                result = sp.run(['git', '-C', wt_path, 'log', '--oneline', '-5'],
                               capture_output=True, text=True)
                print(result.stdout or "No commits")
                continue
            elif action == 't':
                terminal = detect_terminal()
                if terminal:
                    launch_terminal_in_dir(wt_path, terminal)
                    print("✓ Opened terminal")
                continue
            elif action == 'v':
                sp.run(['code', wt_path])
                print("✓ Opened in VSCode")
                continue
            # Action commands
            elif action == '1':
                msg = input("Commit msg (Enter=default): ").strip() or f"Merge {wt_name}"
                if remove_worktree(wt_path, push=True, commit_msg=msg, skip_confirm=True):
                    print("✓ Worktree removed and pushed")
                    break
                else:
                    print("✗ Failed to remove worktree - check project association")
                    continue
            elif action == '2':
                if remove_worktree(wt_path, push=False, skip_confirm=True):
                    print("✓ Worktree removed")
                    break
                else:
                    print("✗ Failed to remove worktree - check project association")
                    continue
            elif action in ['3', '']:
                print("✓ Kept")
                break
            elif action == '4':
                print(f"\n✓ Reviewed {idx+1}/{len(review_worktrees)}")
                # Only kill review sessions, never agent sessions
                if session_to_attach.startswith('review-'):
                    sp.run(['tmux', 'kill-session', '-t', session_to_attach],
                          stdout=sp.DEVNULL, stderr=sp.DEVNULL)
                sys.exit(0)

        # Cleanup only review sessions, never agent sessions
        if session_to_attach.startswith('review-'):
            sp.run(['tmux', 'kill-session', '-t', session_to_attach],
                   stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    print(f"\n✅ Review complete!")
elif arg == 'cleanup':
    # Delete all worktrees without pushing
    if not os.path.exists(WORKTREES_DIR):
        print("No worktrees directory found")
        sys.exit(0)

    worktrees = [d for d in os.listdir(WORKTREES_DIR)
                 if os.path.isdir(os.path.join(WORKTREES_DIR, d))]

    if not worktrees:
        print("No worktrees found")
        sys.exit(0)

    # Show what will be deleted
    print(f"Found {len(worktrees)} worktrees to delete:\n")
    for wt in worktrees:
        print(f"  • {wt}")

    print(f"\n⚠️  This will DELETE all {len(worktrees)} worktrees (no push to git)")

    # Check for --yes flag
    skip_confirm = '--yes' in sys.argv or '-y' in sys.argv

    if not skip_confirm:
        response = input("\nAre you sure? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            print("✗ Cancelled")
            sys.exit(0)
    else:
        print("\n⚠️  Confirmation skipped (--yes flag)")

    print("\n🗑️  Deleting worktrees...\n")

    success_count = 0
    failed_count = 0

    for wt in worktrees:
        worktree_path = os.path.join(WORKTREES_DIR, wt)
        print(f"Deleting: {wt}...")
        if remove_worktree(worktree_path, push=False, skip_confirm=True):
            success_count += 1
            print(f"✓ Deleted {wt}\n")
        else:
            failed_count += 1
            print(f"✗ Failed to delete {wt}\n")

    print(f"\n{'='*60}")
    print(f"✓ Deleted: {success_count}")
    if failed_count > 0:
        print(f"✗ Failed: {failed_count}")
    print(f"{'='*60}")
elif arg == 'p':
    print("Saved Projects & Apps:")
    for i, proj in enumerate(PROJECTS):
        exists = "✓" if os.path.exists(proj) else "✗"
        print(f"  {i}. {exists} {proj}")
    for i, (app_name, app_cmd) in enumerate(APPS):
        # Extract directory from cd commands for cleaner display
        if app_cmd.startswith('cd ') and ' && ' in app_cmd:
            parts = app_cmd.split(' && ', 1)
            dir_path = parts[0].replace('cd ', '').strip()
            # Simplify home directory path
            if dir_path.startswith(os.path.expanduser('~')):
                dir_path = dir_path.replace(os.path.expanduser('~'), '~')
            print(f"  {len(PROJECTS) + i}. {app_name} → {dir_path}")
        else:
            # For non-cd commands, just show the app name and a simplified command
            cmd_display = app_cmd if len(app_cmd) <= 50 else app_cmd[:47] + "..."
            print(f"  {len(PROJECTS) + i}. {app_name} → {cmd_display}")
elif arg == 'add':
    # Add a project to saved list
    if work_dir_arg:
        path = work_dir_arg
    else:
        path = os.getcwd()

    success, message = add_project(path)
    if success:
        print(f"✓ {message}")
        print("\nUpdated project list:")
        # Reload and display projects
        updated_projects = load_projects()
        for i, proj in enumerate(updated_projects):
            exists = "✓" if os.path.exists(proj) else "✗"
            print(f"  {i}. {exists} {proj}")
    else:
        print(f"✗ {message}")
        sys.exit(1)
elif arg == 'remove':
    # Remove a project from saved list
    if not work_dir_arg or not work_dir_arg.isdigit():
        print("✗ Usage: aio remove <project#>")
        print("\nCurrent projects:")
        for i, proj in enumerate(PROJECTS):
            exists = "✓" if os.path.exists(proj) else "✗"
            print(f"  {i}. {exists} {proj}")
        sys.exit(1)

    index = int(work_dir_arg)
    success, message = remove_project(index)
    if success:
        print(f"✓ {message}")
        print("\nUpdated project list:")
        # Reload and display projects
        updated_projects = load_projects()
        for i, proj in enumerate(updated_projects):
            exists = "✓" if os.path.exists(proj) else "✗"
            print(f"  {i}. {exists} {proj}")
    else:
        print(f"✗ {message}")
        sys.exit(1)
elif arg == 'add-app':
    # Add an app to saved list
    # Usage: aio add-app <name> <command>
    if not work_dir_arg:
        print("✗ Usage: aio add-app <name> <command>")
        print("Example: aio add-app vscode \"code ~/projects/myproject\"")
        sys.exit(1)

    # Name is first arg, command is everything else
    app_name = work_dir_arg
    # Get command from remaining arguments
    remaining_args = sys.argv[3:] if len(sys.argv) > 3 else []
    if not remaining_args:
        print("✗ Usage: aio add-app <name> <command>")
        print("Example: aio add-app vscode \"code ~/projects/myproject\"")
        sys.exit(1)

    app_command = ' '.join(remaining_args)

    success, message = add_app(app_name, app_command)
    if success:
        print(f"✓ {message}")
        print("\nUpdated app list:")
        # Reload and display apps
        updated_apps = load_apps()
        for i, (name, cmd) in enumerate(updated_apps):
            print(f"  {i}. [APP] {name}: {cmd}")
    else:
        print(f"✗ {message}")
        sys.exit(1)
elif arg == 'remove-app':
    # Remove an app from saved list
    if not work_dir_arg or not work_dir_arg.isdigit():
        print("✗ Usage: aio remove-app <app#>")
        print("\nCurrent apps:")
        for i, (name, cmd) in enumerate(APPS):
            print(f"  {i}. [APP] {name}: {cmd}")
        sys.exit(1)

    index = int(work_dir_arg)
    success, message = remove_app(index)
    if success:
        print(f"✓ {message}")
        print("\nUpdated app list:")
        # Reload and display apps
        updated_apps = load_apps()
        for i, (name, cmd) in enumerate(updated_apps):
            print(f"  {i}. [APP] {name}: {cmd}")
    else:
        print(f"✗ {message}")
        sys.exit(1)
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
    result = sp.run(['git', '-C', cwd, 'rev-parse', '--git-dir'], capture_output=True, text=True)
    if result.returncode != 0:
        print("✗ Not a git repository")
        sys.exit(1)

    # Check if we're in a worktree
    git_dir = result.stdout.strip()
    is_worktree = '.git/worktrees/' in git_dir or cwd.startswith(WORKTREES_DIR)

    # Get commit message
    commit_msg = work_dir_arg if work_dir_arg else f"Update {os.path.basename(cwd)}"

    if is_worktree:
        # We're in a worktree - need to find the main project and push to main
        worktree_name = os.path.basename(cwd)
        project_path = get_project_for_worktree(cwd)

        if not project_path:
            print(f"✗ Could not determine main project for worktree: {worktree_name}")
            print(f"  Worktree: {cwd}")
            sys.exit(1)

        # Show confirmation dialogue
        print(f"\n📍 You are in a worktree: {worktree_name}")
        print(f"   Main project: {project_path}")
        print(f"\nThis will:")
        print(f"  1. Commit your changes in the worktree")
        print(f"  2. Switch the main project to the main branch")
        print(f"  3. Push to the main branch on remote")
        print(f"  4. Auto-pull to sync main project with remote")
        print(f"  5. Optionally delete the worktree (you'll be asked)")
        print(f"\nCommit message: {commit_msg}")

        skip_confirm = '--yes' in sys.argv or '-y' in sys.argv
        if not skip_confirm:
            response = input("\nContinue? (y/n): ").strip().lower()
            if response not in ['y', 'yes']:
                print("✗ Cancelled")
                sys.exit(0)

        # Get the current branch name in worktree (needed for merging later)
        result = sp.run(['git', '-C', cwd, 'branch', '--show-current'],
                        capture_output=True, text=True)
        worktree_branch = result.stdout.strip()

        # Add and commit changes in worktree
        sp.run(['git', '-C', cwd, 'add', '-A'])
        result = sp.run(['git', '-C', cwd, 'commit', '-m', commit_msg],
                        capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✓ Committed in worktree: {commit_msg}")
        elif 'nothing to commit' in result.stdout or 'no changes added to commit' in result.stdout:
            print("ℹ No changes to commit in worktree")
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            print(f"✗ Commit failed: {error_msg}")
            sys.exit(1)

        # Detect main branch name
        result = sp.run(['git', '-C', project_path, 'symbolic-ref', 'refs/remotes/origin/HEAD'],
                        capture_output=True, text=True)
        if result.returncode == 0:
            main_branch = result.stdout.strip().replace('refs/remotes/origin/', '')
        else:
            result = sp.run(['git', '-C', project_path, 'rev-parse', '--verify', 'main'],
                           capture_output=True)
            main_branch = 'main' if result.returncode == 0 else 'master'

        print(f"→ Switching main project to {main_branch}...")

        # Switch to main branch
        result = sp.run(['git', '-C', project_path, 'checkout', main_branch],
                        capture_output=True, text=True)

        if result.returncode != 0:
            print(f"✗ Failed to switch to {main_branch}: {result.stderr.strip()}")
            sys.exit(1)

        print(f"✓ Switched to {main_branch}")

        # Merge worktree branch into main (auto-resolve conflicts using worktree version)
        print(f"→ Merging {worktree_branch} into {main_branch}...")
        result = sp.run(['git', '-C', project_path, 'merge', worktree_branch, '--no-edit', '-X', 'theirs'],
                        capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            print(f"✗ Merge failed: {error_msg}")
            sys.exit(1)

        print(f"✓ Merged {worktree_branch} into {main_branch} (conflicts auto-resolved)")

        # Push to main
        env = get_noninteractive_git_env()
        result = sp.run(['git', '-C', project_path, 'push', 'origin', main_branch],
                        capture_output=True, text=True, env=env)

        if result.returncode == 0:
            print(f"✓ Pushed to {main_branch}")
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            print(f"✗ Push failed: {error_msg}")
            sys.exit(1)

        # Auto-pull to sync main project with remote
        print(f"→ Syncing main project with remote...")
        env = get_noninteractive_git_env()
        fetch_result = sp.run(['git', '-C', project_path, 'fetch', 'origin'],
                              capture_output=True, text=True, env=env)
        if fetch_result.returncode == 0:
            reset_result = sp.run(['git', '-C', project_path, 'reset', '--hard', f'origin/{main_branch}'],
                                  capture_output=True, text=True)
            if reset_result.returncode == 0:
                print(f"✓ Synced main project with remote")
            else:
                print(f"⚠ Sync warning: {reset_result.stderr.strip()}")
        else:
            print(f"⚠ Fetch warning: {fetch_result.stderr.strip()}")

        # Ask if user wants to delete the worktree
        if not skip_confirm:
            response = input(f"\nDelete worktree '{worktree_name}'? (y/n): ").strip().lower()
            if response in ['y', 'yes']:
                print(f"\n→ Removing worktree: {worktree_name}")

                # Check if we're currently in the worktree being deleted
                try:
                    current_dir = os.getcwd()
                    worktree_path_abs = os.path.abspath(cwd)
                    current_dir_abs = os.path.abspath(current_dir)
                    in_worktree = (current_dir_abs == worktree_path_abs or
                                   current_dir_abs.startswith(worktree_path_abs + os.sep))
                except (FileNotFoundError, OSError):
                    in_worktree = True  # Assume we're in it if we can't determine

                # Remove worktree
                result = sp.run(['git', '-C', project_path, 'worktree', 'remove', '--force', cwd],
                                capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"✓ Removed worktree")
                else:
                    print(f"✗ Failed to remove worktree: {result.stderr.strip()}")
                    sys.exit(1)

                # Delete branch
                branch_name = f"wt-{worktree_name}"
                result = sp.run(['git', '-C', project_path, 'branch', '-D', branch_name],
                                capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"✓ Deleted branch: {branch_name}")

                # Remove directory if still exists
                if os.path.exists(cwd):
                    import shutil
                    shutil.rmtree(cwd)
                    print(f"✓ Deleted directory")

                # If we were in the worktree, spawn a new shell in the safe directory
                if in_worktree:
                    print(f"\n📂 Opening shell in: {project_path}")
                    os.chdir(project_path)
                    os.execvp(os.environ.get('SHELL', '/bin/bash'),
                             [os.environ.get('SHELL', '/bin/bash')])
                else:
                    print(f"✓ Worktree deleted successfully")

    else:
        # Normal repo - regular push behavior
        # Add all changes
        sp.run(['git', '-C', cwd, 'add', '-A'])

        # Commit
        result = sp.run(['git', '-C', cwd, 'commit', '-m', commit_msg],
                        capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Committed: {commit_msg}")
        elif 'nothing to commit' in result.stdout:
            print("ℹ No changes to send")
            sys.exit(0)
        elif 'no changes added to commit' in result.stdout:
            print("ℹ No changes to send")
            print("  (Some files may be ignored or in submodules)")
            sys.exit(0)
        else:
            # Show both stdout and stderr for better error messages
            error_msg = result.stderr.strip() or result.stdout.strip()
            print(f"✗ Commit failed: {error_msg}")
            sys.exit(1)

        # Push
        # Use non-interactive environment to prevent GUI dialogs
        env = get_noninteractive_git_env()
        result = sp.run(['git', '-C', cwd, 'push'], capture_output=True, text=True, env=env)
        if result.returncode == 0:
            print("✓ Pushed to remote")
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            if 'Authentication failed' in error_msg or 'could not read Username' in error_msg or 'Permission denied' in error_msg:
                print(f"❌ Authentication failed. Please set up git credentials:")
                print(f"   • For SSH (recommended):")
                print(f"     1. Check if you have an SSH key: ls ~/.ssh/id_*.pub")
                print(f"     2. If not, generate one: ssh-keygen -t ed25519")
                print(f"     3. Add to GitHub: gh ssh-key add ~/.ssh/id_ed25519.pub")
                print(f"     4. Test: ssh -T git@github.com")
                print(f"   • For HTTPS:")
                print(f"     1. Run: git config --global credential.helper cache")
                print(f"     2. Then: git push (will prompt for username/token)")
                print(f"   • Quick fix: Run 'git push' manually once to authenticate")
            else:
                print(f"✗ Push failed: {error_msg}")
            sys.exit(1)
elif arg == 'pull':
    # Replace local with server version (destructive)
    cwd = os.getcwd()
    result = sp.run(['git', '-C', cwd, 'rev-parse', '--git-dir'], capture_output=True)
    if result.returncode != 0:
        print("✗ Not a git repository")
        sys.exit(1)

    print("⚠ WARNING: This will DELETE all local changes and replace with server version!")
    skip_confirm = '--yes' in sys.argv or '-y' in sys.argv
    if not skip_confirm:
        response = input("Are you sure? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            print("✗ Cancelled")
            sys.exit(0)

    # Use non-interactive environment to prevent GUI dialogs
    env = get_noninteractive_git_env()
    fetch_result = sp.run(['git', '-C', cwd, 'fetch', 'origin'], capture_output=True, text=True, env=env)
    if fetch_result.returncode != 0:
        error_msg = fetch_result.stderr.strip()
        if 'Authentication failed' in error_msg or 'could not read Username' in error_msg or 'Permission denied' in error_msg:
            print(f"❌ Authentication failed. Please set up git credentials:")
            print(f"   • For SSH: Add SSH key to your Git provider")
            print(f"   • For HTTPS: Run 'git config --global credential.helper cache'")
            print(f"   • Then manually 'git fetch' once to save credentials")
            sys.exit(1)
    result = sp.run(['git', '-C', cwd, 'reset', '--hard', 'origin/main'], capture_output=True, text=True)
    if result.returncode != 0:
        result = sp.run(['git', '-C', cwd, 'reset', '--hard', 'origin/master'], capture_output=True, text=True)
    sp.run(['git', '-C', cwd, 'clean', '-f', '-d'], capture_output=True)
    print("✓ Local changes removed. Synced with server.")
elif arg == 'revert':
    # Undo N commits using git revert
    cwd = os.getcwd()
    result = sp.run(['git', '-C', cwd, 'rev-parse', '--git-dir'], capture_output=True)
    if result.returncode != 0:
        print("✗ Not a git repository")
        sys.exit(1)

    num = int(work_dir_arg) if work_dir_arg and work_dir_arg.isdigit() else 1

    # Revert last N commits
    if num == 1:
        # Revert just HEAD
        result = sp.run(['git', '-C', cwd, 'revert', 'HEAD', '--no-edit'],
                       capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Reverted last commit")
        else:
            error = result.stderr.strip() or result.stdout.strip()
            print(f"✗ Revert failed: {error}")
            sys.exit(1)
    else:
        # Revert multiple commits: HEAD~(num-1), HEAD~(num-2), ..., HEAD
        result = sp.run(['git', '-C', cwd, 'revert', f'HEAD~{num}..HEAD', '--no-edit'],
                       capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Reverted last {num} commits")
        else:
            error = result.stderr.strip() or result.stdout.strip()
            print(f"✗ Revert failed: {error}")
            sys.exit(1)
elif arg == 'setup':
    # Initialize git repo with remote
    cwd = os.getcwd()

    # Check if already a repo
    result = sp.run(['git', '-C', cwd, 'rev-parse', '--git-dir'], capture_output=True)
    if result.returncode == 0:
        print("ℹ Already a git repository")
    else:
        sp.run(['git', '-C', cwd, 'init'], capture_output=True)
        print("✓ Initialized git repository")

    # Check if remote exists
    result = sp.run(['git', '-C', cwd, 'remote', 'get-url', 'origin'], capture_output=True)
    has_remote = result.returncode == 0

    # Get remote URL from user if provided as second arg
    remote_url = work_dir_arg

    # If no URL provided and no remote exists, try to help
    if not remote_url and not has_remote:
        # Try using GitHub CLI to create repo automatically
        gh_check = sp.run(['which', 'gh'], capture_output=True)
        if gh_check.returncode == 0:
            print("🚀 No remote configured. Creating GitHub repository...")
            repo_name = os.path.basename(cwd)
            print(f"   Repository name: {repo_name}")

            # Ask for confirmation
            response = input("\n   Create public GitHub repo? (y/n/private): ").strip().lower()
            if response in ['y', 'yes', 'private', 'p']:
                visibility = '--private' if response in ['private', 'p'] else '--public'

                # Create initial commit if needed
                result = sp.run(['git', '-C', cwd, 'rev-parse', 'HEAD'], capture_output=True)
                if result.returncode != 0:
                    sp.run(['git', '-C', cwd, 'add', '-A'], capture_output=True)
                    sp.run(['git', '-C', cwd, 'commit', '-m', 'Initial commit'], capture_output=True)
                    print("✓ Created initial commit")

                # Set main as default branch
                sp.run(['git', '-C', cwd, 'branch', '-M', 'main'], capture_output=True)

                # Create repo and push
                result = sp.run(['gh', 'repo', 'create', repo_name, visibility, '--source=.', '--push'],
                              capture_output=True, text=True)

                if result.returncode == 0:
                    print("✓ Created GitHub repository")
                    print("✓ Added remote origin")
                    print("✓ Pushed to remote")
                    sys.exit(0)
                else:
                    print(f"✗ GitHub repo creation failed: {result.stderr.strip()}")
                    print("\nFalling back to manual setup...")
            else:
                print("✗ Cancelled")
                sys.exit(0)

        # No gh CLI or user wants manual setup - prompt for URL
        print("\n💡 To push your code, add a remote repository:")
        remote_url = input("   Enter remote URL (or press Enter to skip): ").strip()
        if not remote_url:
            print("\n📝 You can add a remote later with:")
            print("   git remote add origin <url>")
            print("   git push -u origin main")
            sys.exit(0)

    if remote_url:
        # Check if remote exists
        result = sp.run(['git', '-C', cwd, 'remote', 'get-url', 'origin'], capture_output=True)
        if result.returncode == 0:
            sp.run(['git', '-C', cwd, 'remote', 'set-url', 'origin', remote_url], capture_output=True)
            print(f"✓ Updated remote origin: {remote_url}")
        else:
            sp.run(['git', '-C', cwd, 'remote', 'add', 'origin', remote_url], capture_output=True)
            print(f"✓ Added remote origin: {remote_url}")

        # Create initial commit if needed
        result = sp.run(['git', '-C', cwd, 'rev-parse', 'HEAD'], capture_output=True)
        if result.returncode != 0:
            sp.run(['git', '-C', cwd, 'add', '-A'], capture_output=True)
            sp.run(['git', '-C', cwd, 'commit', '-m', 'Initial commit'], capture_output=True)
            print("✓ Created initial commit")

        # Set main as default branch and push
        sp.run(['git', '-C', cwd, 'branch', '-M', 'main'], capture_output=True)
        env = get_noninteractive_git_env()
        result = sp.run(['git', '-C', cwd, 'push', '-u', 'origin', 'main'], capture_output=True, text=True, env=env)
        if result.returncode == 0:
            print("✓ Pushed to remote")
        else:
            print("✗ Push failed - you may need to pull first or check permissions")
    elif has_remote:
        # Has remote but no URL provided - just ensure everything is set up
        print("✓ Remote already configured")

        # Create initial commit if needed
        result = sp.run(['git', '-C', cwd, 'rev-parse', 'HEAD'], capture_output=True)
        if result.returncode != 0:
            sp.run(['git', '-C', cwd, 'add', '-A'], capture_output=True)
            sp.run(['git', '-C', cwd, 'commit', '-m', 'Initial commit'], capture_output=True)
            print("✓ Created initial commit")

        # Set main as default branch
        sp.run(['git', '-C', cwd, 'branch', '-M', 'main'], capture_output=True)
        print("✓ Ready to push with: git push -u origin main")
elif arg.endswith('++') and not arg.startswith('w'):
    key = arg[:-2]
    if key in sessions:
        # Determine project path: use specified project or current directory
        if work_dir_arg and work_dir_arg.isdigit():
            idx = int(work_dir_arg)
            if 0 <= idx < len(PROJECTS):
                project_path = PROJECTS[idx]
            else:
                print(f"✗ Invalid project index: {work_dir_arg}")
                sys.exit(1)
        else:
            project_path = work_dir

        base_name, cmd = sessions[key]
        date_str = datetime.now().strftime('%Y%m%d')
        time_str = datetime.now().strftime('%H%M%S')
        name = f"{base_name}-{date_str}-{time_str}-single"

        worktree_result = create_worktree(project_path, name)
        if worktree_result and worktree_result[0]:
            worktree_path = worktree_result[0]
            print(f"✓ Created worktree: {worktree_path}")
            # Use clean environment to prevent GUI dialogs
            env = get_noninteractive_git_env()
            sp.run(['tmux', 'new', '-d', '-s', name, '-c', worktree_path, cmd], env=env)

            if new_window:
                launch_in_new_window(name)
                if with_terminal:
                    launch_terminal_in_dir(worktree_path)
            elif "TMUX" in os.environ:
                # Already inside tmux - let session run in background
                print(f"✓ Session running in background: {name}")
                print(f"   Switch to it: tmux switch-client -t {name}")
            else:
                # Not in tmux - attach normally
                os.execvp('tmux', ['tmux', 'attach', '-t', name])
    else:
        print(f"✗ Unknown session key: {key}")
# Removed old '+' feature (timestamped session without worktree)
# to make room for new '+' and '++' worktree commands
else:
    # Try directory-based session logic first
    session_name = get_or_create_directory_session(arg, work_dir)

    if session_name is None:
        # Not a known session key, use original behavior
        name, cmd = sessions.get(arg, (arg, None))
        # Use clean environment to prevent GUI dialogs
        env = get_noninteractive_git_env()
        sp.run(['tmux', 'new', '-d', '-s', name, '-c', work_dir, cmd or arg], capture_output=True, env=env)
        session_name = name
    else:
        # Got a directory-specific session name
        # Check if it exists, create if not
        check_result = sp.run(['tmux', 'has-session', '-t', session_name],
                             capture_output=True)
        if check_result.returncode != 0:
            # Session doesn't exist, create it
            _, cmd = sessions[arg]
            # Use clean environment to prevent GUI dialogs
            env = get_noninteractive_git_env()
            sp.run(['tmux', 'new', '-d', '-s', session_name, '-c', work_dir, cmd],
                  capture_output=True, env=env)

    # Check if this is a single-p session (cp, lp, gp but not cpp, lpp, gpp)
    is_single_p_session = arg.endswith('p') and not arg.endswith('pp') and len(arg) == 2 and arg in sessions

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
        if sys.argv[i] not in ['-w', '--new-window', '--yes', '-y', '-t', '--with-terminal']:
            prompt_parts.append(sys.argv[i])

    if prompt_parts:
        # Custom prompt provided on command line
        prompt = ' '.join(prompt_parts)
        print(f"📤 Sending prompt to session...")
        send_prompt_to_session(session_name, prompt, wait_for_completion=False, wait_for_ready=True, send_enter=not is_single_p_session)
    elif is_single_p_session:
        # Single-p session without custom prompt - insert default prompt without running
        # Map session key to prompt config key
        prompt_map = {'cp': CODEX_PROMPT, 'lp': CLAUDE_PROMPT, 'gp': GEMINI_PROMPT}
        default_prompt = prompt_map.get(arg, '')
        if default_prompt:
            print(f"📝 Inserting default prompt into session...")
            send_prompt_to_session(session_name, default_prompt, wait_for_completion=False, wait_for_ready=True, send_enter=False)

    if new_window:
        launch_in_new_window(session_name)
        # Also launch a regular terminal if requested
        if with_terminal:
            launch_terminal_in_dir(work_dir)
    elif "TMUX" in os.environ:
        # Already inside tmux - let session run in background
        print(f"✓ Session running in background: {session_name}")
        print(f"   Switch to it: tmux switch-client -t {session_name}")
    else:
        # Not in tmux - attach normally
        os.execvp('tmux', ['tmux', 'attach', '-t', session_name])
