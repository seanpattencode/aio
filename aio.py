#!/usr/bin/env python3
import os, sys, subprocess as sp, json
import sqlite3
from datetime import datetime
from pathlib import Path
import shlex
import shutil
import time

# Optional dependencies - graceful fallback if not installed
try:
    import pexpect
    HAS_PEXPECT = True
except ImportError:
    HAS_PEXPECT = False

try:
    from prompt_toolkit import Application
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.widgets import TextArea, Frame
    from prompt_toolkit.key_binding import KeyBindings
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

def input_box(prefill="", title="Ctrl+D to run"):
    # Fallback to simple input inside tmux, non-TTY, or if prompt_toolkit not installed
    if not sys.stdin.isatty() or 'TMUX' in os.environ or not HAS_PROMPT_TOOLKIT:
        print(f"[{title}] " if not prefill else f"[{title}]\n{prefill}\n> ", end="", flush=True)
        return input() if not prefill else prefill
    kb = KeyBindings()
    @kb.add('c-d')
    def _(e): e.app.exit()
    ta = TextArea(text=prefill, multiline=True, focus_on_click=True)
    Application(layout=Layout(Frame(ta, title=title)), key_bindings=kb, full_screen=True, mouse_support=True).run()
    return ta.text

# Session Manager - generic multiplexer abstraction (tmux implementation)
class Multiplexer:
    """Generic terminal multiplexer interface. Override methods for other implementations."""
    def new_session(self, n, d, c, e=None): raise NotImplementedError
    def send_keys(self, n, t): raise NotImplementedError
    def attach(self, n): raise NotImplementedError
    def has_session(self, n): raise NotImplementedError
    def list_sessions(self): raise NotImplementedError
    def capture(self, n): raise NotImplementedError

class TmuxManager(Multiplexer):
    """Tmux multiplexer with enhanced options (scrollbars, mouse mode, keybindings)."""
    def __init__(self):
        self._ver = sp.check_output(['tmux', '-V'], text=True).split()[1] if shutil.which('tmux') else '0'
    def new_session(self, n, d, c, e=None): return sp.run(['tmux', 'new-session', '-d', '-s', n, '-c', d] + ([c] if c else []), capture_output=True, env=e)
    def send_keys(self, n, t): return sp.run(['tmux', 'send-keys', '-l', '-t', n, t])
    def attach(self, n): return ['tmux', 'attach', '-t', n]
    def has_session(self, n): return sp.run(['tmux', 'has-session', '-t', n], capture_output=True).returncode == 0
    def list_sessions(self): return sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True)
    def capture(self, n): return sp.run(['tmux', 'capture-pane', '-p', '-t', n], capture_output=True, text=True)
    @property
    def version(self): return self._ver

sm = TmuxManager()
# Auto-update tmux every 12h in background (installs to ~/.local, zero lag)
try:
    _ts_dir = os.path.expanduser('~/.local/share/aios'); os.makedirs(_ts_dir, exist_ok=True)
    _ts = os.path.join(_ts_dir, '.tmux_update')
    ((not os.path.exists(_ts) or time.time()-os.path.getmtime(_ts)>43200) and os.fork()==0) and (Path(_ts).touch(),os.system(f'v=$(curl -sL api.github.com/repos/tmux/tmux/releases/latest 2>/dev/null|grep -oP \'"tag_name":"\\K[^"]+\');[ "$v" \\> "{sm.version}" ]&&cd /tmp&&rm -rf tmux-update&&git clone -q --depth 1 -b $v https://github.com/tmux/tmux tmux-update 2>/dev/null&&cd tmux-update&&sh autogen.sh>/dev/null 2>&1&&./configure --prefix=$HOME/.local>/dev/null 2>&1&&make -j$(nproc)>/dev/null 2>&1&&make install>/dev/null 2>&1'),os._exit(0))
except: pass

# Auto-update: Pull latest version from git repo
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))  # realpath follows symlinks
PROMPTS_FILE = os.path.join(SCRIPT_DIR, 'data', 'prompts.json')
DEFAULT_PROMPTS = {
    "fix": "Analyze codebase, find issues, fix them.",
    "bug": "Fix this bug: {task}. Minimize line count, use direct library calls only.",
    "feat": "Add this feature: {task}. Use library glue, minimize line count.",
    "auto": "Auto-improve: find pain points, simplify, rewrite with more library calls.",
    "del": "Deletion mode: delete aggressively, add back only what user fights for.",
    "gen": "Guidelines: minimize line count, maximize speed, use direct library calls only."
}

def load_prompts():
    try:
        with open(PROMPTS_FILE) as f: return {**DEFAULT_PROMPTS, **json.load(f)}
    except: return DEFAULT_PROMPTS

def manual_update():
    """Update aio from git repository - explicit user command only."""
    # Check if we're in a git repo
    result = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', '--git-dir'],
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    if result.returncode != 0:
        print("✗ Not in a git repository")
        return False

    print("🔄 Checking for updates...")

    # Get current commit hash
    before = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', 'HEAD'],
                    capture_output=True, text=True)

    if before.returncode != 0:
        print("✗ Failed to get current version")
        return False

    before_hash = before.stdout.strip()[:8]  # Short hash

    # Fetch to see if there are updates
    fetch_result = sp.run(['git', '-C', SCRIPT_DIR, 'fetch'],
                         capture_output=True, text=True)

    if fetch_result.returncode != 0:
        print(f"✗ Failed to check for updates: {fetch_result.stderr.strip()}")
        return False

    # Check if we're behind
    status = sp.run(['git', '-C', SCRIPT_DIR, 'status', '-uno'],
                    capture_output=True, text=True)

    if 'Your branch is behind' not in status.stdout:
        print(f"✓ Already up to date (version {before_hash})")
        return True

    # Pull latest changes
    print("⬇️  Downloading updates...")
    pull_result = sp.run(['git', '-C', SCRIPT_DIR, 'pull', '--ff-only'],
                        capture_output=True, text=True)

    if pull_result.returncode != 0:
        print(f"✗ Update failed: {pull_result.stderr.strip()}")
        print("💡 Try: git pull --rebase")
        return False

    # Get new commit hash
    after = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', 'HEAD'],
                   capture_output=True, text=True)

    if after.returncode == 0:
        after_hash = after.stdout.strip()[:8]
        print(f"✅ Updated: {before_hash} → {after_hash}")
        print("🔄 Please run your command again to use the new version")
        # Clear update marker
        try: os.remove(os.path.join(os.path.expanduser('~/.local/share/aios'), '.update_available'))
        except: pass
        return True

    return True

# No auto-update - Git philosophy: explicit updates only
# But warn user if remote has newer version (check every 30 min, forked to avoid lag)
def check_for_updates_warning():
    """Background check for newer git version, warns user if behind."""
    ts_file = os.path.join(os.path.expanduser('~/.local/share/aios'), '.update_check')
    # Only check every 30 minutes
    if os.path.exists(ts_file) and time.time() - os.path.getmtime(ts_file) < 1800:
        return
    if not hasattr(os, 'fork') or os.fork() != 0:
        return  # Parent returns immediately, child continues
    try:
        Path(ts_file).touch()
        # Quick fetch to check for updates
        result = sp.run(['git', '-C', SCRIPT_DIR, 'fetch', '--dry-run'],
                       capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stderr.strip():
            # There are updates available - write marker file
            marker = os.path.join(os.path.expanduser('~/.local/share/aios'), '.update_available')
            Path(marker).touch()
    except: pass
    os._exit(0)

def show_update_warning():
    """Show warning if updates are available (called at startup)."""
    marker = os.path.join(os.path.expanduser('~/.local/share/aios'), '.update_available')
    if os.path.exists(marker):
        # Verify still behind by checking status
        result = sp.run(['git', '-C', SCRIPT_DIR, 'status', '-uno'],
                       capture_output=True, text=True)
        if 'Your branch is behind' in result.stdout:
            print("⚠️  Update available! Run 'aio update' to get latest version")
        else:
            # No longer behind, remove marker
            try: os.remove(marker)
            except: pass

# Trigger background update check
try:
    check_for_updates_warning()
except: pass

def ensure_git_config():
    """Auto-configure git user from GitHub credentials if not set."""
    # Check if already configured
    name = sp.run(['git', 'config', 'user.name'], capture_output=True, text=True)
    email = sp.run(['git', 'config', 'user.email'], capture_output=True, text=True)
    if name.returncode == 0 and email.returncode == 0 and name.stdout.strip() and email.stdout.strip():
        return True
    # Try to get from gh (GitHub CLI)
    if not shutil.which('gh'):
        return False
    try:
        result = sp.run(['gh', 'api', 'user'], capture_output=True, text=True)
        if result.returncode != 0:
            return False
        import json as _json
        user = _json.loads(result.stdout)
        gh_name = user.get('name') or user.get('login', '')
        gh_login = user.get('login', '')
        gh_email = user.get('email') or f"{gh_login}@users.noreply.github.com"
        if gh_name and not name.stdout.strip():
            sp.run(['git', 'config', '--global', 'user.name', gh_name], capture_output=True)
        if gh_email and not email.stdout.strip():
            sp.run(['git', 'config', '--global', 'user.email', gh_email], capture_output=True)
        return True
    except:
        return False

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

            conn.execute("""
                CREATE TABLE IF NOT EXISTS multi_runs (
                    id TEXT PRIMARY KEY,
                    repo TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    agents TEXT NOT NULL,
                    status TEXT DEFAULT 'running',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    review_rank TEXT
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

            # Add reviewer prompt if not exists
            cursor = conn.execute("SELECT COUNT(*) FROM prompts WHERE name = 'reviewer'")
            if cursor.fetchone()[0] == 0:
                reviewer_prompt = """You are reviewing code implementations for: {TASK}

Agents used: {AGENTS}
Directories to review: {DIRS}

You do NOT edit code. Run tests to verify. Rank by:
1. Runs without errors
2. Solves the problem
3. Shortest code (fewer lines)
4. Most library calls (library glue pattern)
5. Fastest execution

Create REVIEW.md with:
# Review Results
## Ranking
1. [best] - reason
2. [next] - reason

## Recommendation
Which to push to main and why.

Say REVIEW COMPLETE when done."""
                conn.execute("INSERT INTO prompts VALUES ('reviewer', ?)", (reviewer_prompt,))

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

_tmux_configured = False
def ensure_tmux_options():
    """Configure tmux: 2-line status bar, mouse, scrollbars, keyboard shortcuts."""
    global _tmux_configured
    if _tmux_configured: return
    if sp.run(['tmux', 'info'], stdout=sp.DEVNULL, stderr=sp.DEVNULL).returncode != 0: return
    # Status bar on top, mouse mode, 2-line status (tmux 2.9+)
    for opt in [('mouse', 'on'), ('status-position', 'top'), ('status', '2')]:
        sp.run(['tmux', 'set-option', '-g', opt[0], opt[1]], capture_output=True)
    # Scrollbars (tmux 3.6+)
    if sm.version >= '3.6':
        sp.run(['tmux', 'set-option', '-g', 'pane-scrollbars', 'on'], capture_output=True)
        sp.run(['tmux', 'set-option', '-g', 'pane-scrollbars-position', 'right'], capture_output=True)
    # Copy mode: mouse drag copies to clipboard
    for mode in ['copy-mode', 'copy-mode-vi']:
        sp.run(['tmux', 'bind-key', '-T', mode, 'MouseDragEnd1Pane', 'send-keys', '-X', 'copy-pipe-and-cancel', 'xclip -sel clip'], capture_output=True)
    # Keyboard shortcuts: Ctrl+T new, Ctrl+W close, Ctrl+Q detach, Ctrl+X kill session
    for k, a in [('C-t', 'split-window'), ('C-w', 'kill-pane'), ('C-q', 'detach')]:
        sp.run(['tmux', 'bind-key', '-n', k, a], capture_output=True)
    sp.run(['tmux', 'bind-key', '-n', 'C-x', 'confirm-before', '-p', 'Kill session? (y/n)', 'kill-session'], capture_output=True)

    # 2-line status bar layout:
    # Line 0: Session name (left) + window list (center) - NO status-right
    # Line 1: Keyboard shortcuts (centered) with responsive width detection

    # Line 0: Clean session/window display only (no status-right to avoid overlap)
    # Format: [session] window-list
    line0 = '#[align=left][#S]#[align=centre]#{W:#I:#W#{?window_active,*, } }'
    sp.run(['tmux', 'set-option', '-g', 'status-format[0]', line0], capture_output=True)

    # Line 1: Shortcuts with 3-tier responsive width detection
    # <45: minimal (^T ^W ^X ^Q), 45-70: short labels, >70: full labels
    if sm.version >= '3.2':
        # Clickable shortcuts with range markers
        sh_full = '#[range=user|new]Ctrl+T:New#[norange] #[range=user|close]Ctrl+W:Close#[norange] #[range=user|kill]Ctrl+X:Kill#[norange] #[range=user|detach]Ctrl+Q:Detach#[norange]'
        sh_med = '#[range=user|new]^T:New#[norange] #[range=user|close]^W:Close#[norange] #[range=user|kill]^X:Kill#[norange] #[range=user|detach]^Q:Quit#[norange]'
        sh_min = '#[range=user|new]^T#[norange] #[range=user|close]^W#[norange] #[range=user|kill]^X#[norange] #[range=user|detach]^Q#[norange]'
        # Mouse click binding
        click_binding = "if -F '#{==:#{mouse_status_range},new}' { split-window } { if -F '#{==:#{mouse_status_range},close}' { kill-pane } { if -F '#{==:#{mouse_status_range},kill}' { confirm-before -p 'Kill?' kill-session } { if -F '#{==:#{mouse_status_range},detach}' { detach } { if -F '#{==:#{mouse_status_range},window}' { select-window } } } } }"
        sp.run(['tmux', 'bind-key', '-Troot', 'MouseDown1Status', click_binding], capture_output=True)
    else:
        sh_full = 'Ctrl+T:New Ctrl+W:Close Ctrl+X:Kill Ctrl+Q:Detach'
        sh_med = '^T:New ^W:Close ^X:Kill ^Q:Quit'
        sh_min = '^T ^W ^X ^Q'

    # Nested conditional: #{?#{e|<:width,45},MIN,#{?#{e|<:width,70},MED,FULL}}
    line1 = '#{?#{e|<:#{client_width},45},' + sh_min + ',#{?#{e|<:#{client_width},70},' + sh_med + ',' + sh_full + '}}'
    sp.run(['tmux', 'set-option', '-g', 'status-format[1]', '#[align=centre]' + line1], capture_output=True)

    # Clear status-right since we're using status-format now
    sp.run(['tmux', 'set-option', '-g', 'status-right', ''], capture_output=True)
    _tmux_configured = True

# Apply tmux options immediately if tmux is running
ensure_tmux_options()

def create_tmux_session(session_name, work_dir, cmd, env=None, capture_output=True):
    """Create a tmux session with enhanced options. Agent sessions get agent+bash panes."""
    ensure_tmux_options()
    result = sm.new_session(session_name, work_dir, cmd or '', env)
    # Status bar configured globally via status-format[1] in ensure_tmux_options()
    # Auto-add bash pane for agent sessions (bash left, agent right)
    if cmd and any(a in cmd for a in ['codex', 'claude', 'gemini']):
        sp.run(['tmux', 'split-window', '-bh', '-t', session_name, '-c', work_dir], capture_output=True)
        sp.run(['tmux', 'select-pane', '-t', session_name, '-R'], capture_output=True)
    return result

def detect_terminal():
    """Detect available terminal emulator"""
    for term in ['ptyxis', 'gnome-terminal', 'alacritty']:
        if shutil.which(term):
            return term
    return None

# Font size controller - generic architecture with terminal-specific implementations
class FontController:
    """Base class for terminal font size control."""
    name = "unknown"

    @classmethod
    def detect(cls) -> bool:
        """Return True if this terminal is detected."""
        return False

    @classmethod
    def get_size(cls) -> int | None:
        """Get current font size, or None if unavailable."""
        return None

    @classmethod
    def set_size(cls, size: int) -> bool:
        """Set font size. Returns True on success."""
        return False

    @classmethod
    def adjust(cls, delta: int) -> bool:
        """Adjust font size by delta. Returns True on success."""
        current = cls.get_size()
        if current is not None:
            return cls.set_size(current + delta)
        return False

    @classmethod
    def show_help(cls):
        """Show help for manual font adjustment."""
        print("Font size control not available for this terminal.")

class TermuxFont(FontController):
    """Termux font controller - provides guidance since no API exists."""
    name = "termux"

    @classmethod
    def detect(cls) -> bool:
        return os.environ.get('TERMUX_VERSION') is not None

    @classmethod
    def get_size(cls) -> int | None:
        # Termux doesn't expose current font size
        return None

    @classmethod
    def set_size(cls, size: int) -> bool:
        # No programmatic control available
        print(f"⚠️  Termux doesn't support programmatic font size control.")
        cls.show_help()
        return False

    @classmethod
    def adjust(cls, delta: int) -> bool:
        direction = "larger" if delta > 0 else "smaller"
        print(f"To make text {direction}:")
        cls.show_help()
        return False

    @classmethod
    def show_help(cls):
        print("""
╔═══════════════════════════════════════════════════════╗
║  TERMUX FONT SIZE                                     ║
╠═══════════════════════════════════════════════════════╣
║  📱 Touch: Pinch to zoom in/out                       ║
║  ⌨️  Keys:  Ctrl+Alt++ (larger) Ctrl+Alt+- (smaller)  ║
║  💡 Tip:   Volume keys may also work on some devices  ║
╚═══════════════════════════════════════════════════════╝""")

class GnomeTerminalFont(FontController):
    """GNOME Terminal font controller using gsettings."""
    name = "gnome-terminal"

    @classmethod
    def detect(cls) -> bool:
        return (os.environ.get('GNOME_TERMINAL_SCREEN') is not None or
                os.environ.get('VTE_VERSION') is not None) and shutil.which('gsettings')

    @classmethod
    def _get_profile(cls) -> str | None:
        """Get the default profile UUID."""
        try:
            result = sp.run(['gsettings', 'get', 'org.gnome.Terminal.ProfilesList', 'default'],
                          capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().strip("'")
        except: pass
        return None

    @classmethod
    def get_size(cls) -> int | None:
        profile = cls._get_profile()
        if not profile:
            return None
        try:
            result = sp.run(['gsettings', 'get',
                           f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{profile}/',
                           'font'], capture_output=True, text=True)
            if result.returncode == 0:
                # Font string like "'Monospace 12'"
                font = result.stdout.strip().strip("'")
                size = int(font.split()[-1])
                return size
        except: pass
        return None

    @classmethod
    def set_size(cls, size: int) -> bool:
        profile = cls._get_profile()
        if not profile:
            return False
        try:
            # Get current font name
            result = sp.run(['gsettings', 'get',
                           f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{profile}/',
                           'font'], capture_output=True, text=True)
            if result.returncode == 0:
                font = result.stdout.strip().strip("'")
                font_name = ' '.join(font.split()[:-1])
                new_font = f"{font_name} {size}"
                sp.run(['gsettings', 'set',
                       f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{profile}/',
                       'font', new_font], capture_output=True)
                print(f"✓ Font size set to {size}")
                return True
        except: pass
        return False

    @classmethod
    def show_help(cls):
        print("GNOME Terminal: Use Ctrl+Shift++ / Ctrl+- or Edit → Preferences → Profiles")

class AlacrittyFont(FontController):
    """Alacritty font controller using config file."""
    name = "alacritty"
    config_paths = [
        os.path.expanduser("~/.config/alacritty/alacritty.toml"),
        os.path.expanduser("~/.config/alacritty/alacritty.yml"),
        os.path.expanduser("~/.alacritty.toml"),
        os.path.expanduser("~/.alacritty.yml"),
    ]

    @classmethod
    def detect(cls) -> bool:
        return os.environ.get('ALACRITTY_WINDOW_ID') is not None

    @classmethod
    def _get_config_path(cls) -> str | None:
        for path in cls.config_paths:
            if os.path.exists(path):
                return path
        return None

    @classmethod
    def get_size(cls) -> int | None:
        config = cls._get_config_path()
        if not config:
            return None
        try:
            with open(config) as f:
                content = f.read()
            # Simple regex for size in TOML or YAML
            import re
            match = re.search(r'size\s*[=:]\s*(\d+(?:\.\d+)?)', content)
            if match:
                return int(float(match.group(1)))
        except: pass
        return None

    @classmethod
    def set_size(cls, size: int) -> bool:
        config = cls._get_config_path()
        if not config:
            # Create default config
            config = cls.config_paths[0]
            os.makedirs(os.path.dirname(config), exist_ok=True)
            with open(config, 'w') as f:
                f.write(f'[font]\nsize = {size}\n')
            print(f"✓ Created {config} with font size {size}")
            return True
        try:
            with open(config) as f:
                content = f.read()
            import re
            if re.search(r'size\s*[=:]\s*\d+', content):
                new_content = re.sub(r'(size\s*[=:]\s*)\d+(?:\.\d+)?', f'\\g<1>{size}', content)
            else:
                # Add font size section
                if config.endswith('.toml'):
                    new_content = content + f'\n[font]\nsize = {size}\n'
                else:
                    new_content = content + f'\nfont:\n  size: {size}\n'
            with open(config, 'w') as f:
                f.write(new_content)
            print(f"✓ Font size set to {size} (Alacritty auto-reloads)")
            return True
        except Exception as e:
            print(f"✗ Failed: {e}")
        return False

    @classmethod
    def show_help(cls):
        print("Alacritty: Use Ctrl+= / Ctrl+- or edit ~/.config/alacritty/alacritty.toml")

class KittyFont(FontController):
    """Kitty font controller using remote control."""
    name = "kitty"

    @classmethod
    def detect(cls) -> bool:
        return os.environ.get('KITTY_WINDOW_ID') is not None

    @classmethod
    def get_size(cls) -> int | None:
        try:
            result = sp.run(['kitty', '@', 'get-colors'], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'font_size' in line:
                        return int(float(line.split()[-1]))
        except: pass
        return None

    @classmethod
    def set_size(cls, size: int) -> bool:
        try:
            result = sp.run(['kitty', '@', 'set-font-size', str(size)], capture_output=True)
            if result.returncode == 0:
                print(f"✓ Font size set to {size}")
                return True
        except: pass
        return False

    @classmethod
    def show_help(cls):
        print("Kitty: Use Ctrl+Shift+= / Ctrl+Shift+- or 'kitty @ set-font-size SIZE'")

# Ordered list of font controllers (checked in order)
FONT_CONTROLLERS = [TermuxFont, KittyFont, AlacrittyFont, GnomeTerminalFont]

def get_font_controller() -> FontController | None:
    """Detect and return the appropriate font controller."""
    for controller in FONT_CONTROLLERS:
        if controller.detect():
            return controller
    return None

def handle_font_command(args: list):
    """Handle 'aio font' command."""
    controller = get_font_controller()

    if not controller:
        print("✗ Unknown terminal. Supported: Termux, Kitty, Alacritty, GNOME Terminal")
        return

    print(f"Terminal: {controller.name}")

    if not args:
        # Show current size or help
        size = controller.get_size()
        if size:
            print(f"Current font size: {size}")
        else:
            controller.show_help()
        return

    arg = args[0]

    if arg == '+' or arg == 'up' or arg == 'bigger':
        delta = int(args[1]) if len(args) > 1 else 2
        controller.adjust(delta)
    elif arg == '-' or arg == 'down' or arg == 'smaller':
        delta = int(args[1]) if len(args) > 1 else 2
        controller.adjust(-delta)
    elif arg.isdigit():
        controller.set_size(int(arg))
    elif arg == 'help':
        controller.show_help()
    else:
        print(f"Usage: aio font [+|-|SIZE|help]")
        print(f"  aio font        Show current size or help")
        print(f"  aio font +      Increase by 2")
        print(f"  aio font -      Decrease by 2")
        print(f"  aio font + 4    Increase by 4")
        print(f"  aio font 16     Set to size 16")
        print(f"  aio font help   Show terminal-specific help")

def launch_in_new_window(session_name, terminal=None):
    """Launch tmux session in new terminal window"""
    if not terminal:
        terminal = detect_terminal()

    if not terminal:
        print("✗ No supported terminal found (ptyxis, gnome-terminal, alacritty)")
        return False

    attach_cmd = sm.attach(session_name)
    if terminal == 'ptyxis':
        cmd = ['ptyxis', '--'] + attach_cmd
    elif terminal == 'gnome-terminal':
        cmd = ['gnome-terminal', '--'] + attach_cmd
    elif terminal == 'alacritty':
        cmd = ['alacritty', '-e'] + attach_cmd

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
    if not HAS_PEXPECT:
        print("✗ pexpect not installed. Run: aio deps")
        return (1, "pexpect not installed")
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
    if not sm.has_session(session_name):
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
    # Use session manager to send keys
    sm.send_keys(session_name, prompt)

    if send_enter:
        time.sleep(0.1)  # Brief delay before Enter for terminal processing
        sm.send_keys(session_name, '\n')
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
    result = sm.list_sessions()

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
        if not sm.has_session(final_session_name):
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
             if os.path.isdir(os.path.join(WORKTREES_DIR, d)) and
             os.path.exists(os.path.join(WORKTREES_DIR, d, '.git'))]

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
        print(f"⚠️  WARNING: This will PUSH changes to the main branch!")
        print(f"Action: Remove worktree, delete branch, AND PUSH to origin/main")
        if commit_msg:
            print(f"Commit message: {commit_msg}")
    else:
        print(f"Action: Remove worktree and delete branch (local only, no push)")

    # Push operations ALWAYS require explicit confirmation for safety
    if push:
        # Always require confirmation for push, even with --yes flag
        response = input("\n⚠️  CONFIRM PUSH TO MAIN? Type 'yes' to continue: ").strip().lower()
        if response != 'yes':
            print("✗ Cancelled (must type 'yes' for push operations)")
            return False
    elif not skip_confirm:
        # Non-push operations can be skipped with --yes
        response = input("\nAre you sure? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            print("✗ Cancelled")
            return False
    else:
        # Only for non-push operations with --yes flag
        print("\n⚠ Confirmation skipped (--yes flag)")

    print(f"\nRemoving worktree: {worktree_name}")

    # Git worktree remove (with --force to handle modified/untracked files)
    result = sp.run(['git', '-C', project_path, 'worktree', 'remove', '--force', worktree_path],
                    capture_output=True, text=True)

    if result.returncode != 0:
        # Check if this is a corrupted worktree (main working tree error)
        if 'is a main working tree' in result.stderr:
            print(f"⚠ Detected corrupted worktree (may be symlink or standalone repo)")
            # Safety check: only delete if it's actually in the worktrees directory
            if worktree_path.startswith(WORKTREES_DIR):
                import shutil
                try:
                    # Check if it's a symlink
                    if os.path.islink(worktree_path):
                        os.unlink(worktree_path)
                        print(f"✓ Removed symlink worktree")
                    else:
                        # It's a corrupted standalone repository
                        shutil.rmtree(worktree_path)
                        print(f"✓ Removed corrupted worktree directory")

                    # Try to clean up any dangling worktree references in parent repo
                    prune_result = sp.run(['git', '-C', project_path, 'worktree', 'prune'],
                                        capture_output=True, text=True)
                    if prune_result.returncode == 0:
                        print(f"✓ Pruned worktree references")

                    # For corrupted worktrees, skip branch deletion and return success
                    return True
                except Exception as e:
                    print(f"✗ Failed to remove directory: {e}")
                    return False
            else:
                print(f"✗ Safety check failed: not in worktrees directory")
                return False
        else:
            print(f"✗ Failed to remove worktree: {result.stderr.strip()}")
            return False
    else:
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

# Show update warning if available (non-blocking check was done at import time)
show_update_warning()
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

# Auto-backup check disabled for instant startup
# auto_backup_check()

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

def format_app_command(app_cmd, max_length=60):
    """Format app command for display, truncating if necessary."""
    # Simplify home directory paths
    display_cmd = app_cmd.replace(os.path.expanduser('~'), '~')

    # Truncate if too long
    if len(display_cmd) > max_length:
        display_cmd = display_cmd[:max_length-3] + "..."

    return display_cmd

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

        # Display what we're running
        cmd_display = format_app_command(app_command)
        print(f"▶️  Running: {app_name}")
        print(f"   Command: {cmd_display}")

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
            # Join all remaining args as commit message (supports both quoted and unquoted)
            remaining_args = [a for a in sys.argv[2:] if a not in ['--yes', '-y']]
            commit_msg = ' '.join(remaining_args) if remaining_args else None
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
    print(f"""aio - AI agent session manager
QUICK START:
  aio c               Start codex (c=codex l=claude g=gemini)
  aio fix             AI finds/fixes issues
  aio bug "task"      Fix a bug
  aio feat "task"     Add a feature
MULTI-AGENT:
  aio multi c:3             Launch 3 codex in parallel worktrees
  aio multi c:3 "task"      Launch 3 codex with custom task
  aio multi c:2 l:1         Mixed: 2 codex + 1 claude
  aio multi 0 c:2 "task"    Launch in project 0
GIT:
  aio push ["msg"]    Commit and push
  aio pull            Sync with server
MANAGEMENT:
  aio jobs            Show active jobs
  aio attach          Reconnect to session
  aio killall         Kill all tmux sessions
  aio cleanup         Delete all worktrees
  aio prompt [name]   Edit prompts (feat, fix, bug, auto, del)
  aio add [path]      Add project
  aio remove <#>      Remove project
  aio app add <name>  Add app
  aio app rm <#>      Remove app
Run 'aio help' for all commands""")
    if PROJECTS or APPS:
        if PROJECTS:
            print("📁 PROJECTS (use 'aio <#>' to open):")
            for i, proj in enumerate(PROJECTS):
                exists = "✓" if os.path.exists(proj) else "✗"
                print(f"  {i}. {exists} {proj}")

        if APPS:
            if PROJECTS:
                print("")  # Add blank line between sections
            print("⚡ APPS (use 'aio <#>' to run):")
            for i, (app_name, app_cmd) in enumerate(APPS):
                cmd_display = format_app_command(app_cmd)
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
CUSTOM PROMPTS (predefined workflows)
═══════════════════════════════════════════════════════════════════════════════
  aio fix                Autonomous: find/fix issues (11-step protocol)
  aio bug "task"         Fix bug: read, run, research best practices, fix
  aio feat "task"        Add feature: library glue pattern, minimal code
  aio auto               Auto-improve: find pain, simplify, rewrite better
  aio del                Deletion: delete aggressively, add back only essentials
AGENT SELECTION (optional, default=claude):
  aio bug c "task"       Use codex for bug fix
  aio feat l "task"      Use claude for feature
  aio auto g             Use gemini for auto-improve
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
  aio attach             Reconnect to multi-agent session
  aio killall            Kill all tmux sessions (keeps current if inside tmux)
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
  aio deps               Install dependencies (node, codex, claude, gemini)
  aio update             Update aio to latest version from git
  aio font [+|-|SIZE]    Adjust terminal font size (Termux/Kitty/Alacritty/GNOME)
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
APP MANAGEMENT
═══════════════════════════════════════════════════════════════════════════════
Apps are custom commands you can run quickly with aio:
• List apps: aio app
• Add app: aio app add <name> [command]
  - Automatically includes current directory (if not in home)
  - If no command given, prompts interactively
  - Removes square brackets if accidentally included
  - Example from ~/projects/myapp: aio app add test 'pytest'
    Creates: cd ~/projects/myapp && pytest
  - Example: aio app add server 'python -m http.server 8000'
• Add globally: aio app add <name> --global <command>
  - Skips directory context, runs from anywhere
  - Use for commands that should work everywhere
  - Example: aio app add docker --global 'docker ps -a'
• Edit app: aio app edit <#|name>
  - Can use app number or name
  - Prompts for new command interactively
• Remove app: aio app rm <#|name>
  - Removes app with confirmation
• Run app: aio <#>
  - Use the app's number from the list
═══════════════════════════════════════════════════════════════════════════════
EXAMPLES
═══════════════════════════════════════════════════════════════════════════════
Getting Started:
  aio install              Make 'aio' globally available
  aio update               Check for and install updates
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
• Run 'aio update' to pull latest version from git
• Auto-backup every 10 minutes (silent, zero delay, stored in ~/.local/share/aios)
• Works in any git directory for push/worktree commands
• Mouse mode enabled: Hold Shift to select and copy text
• Database stores: projects, sessions, prompts, configuration
Working directory: {WORK_DIR}
""")
    if PROJECTS:
        print("📁 PROJECTS (examples: 'aio 0' opens project 0):")
        for i, proj in enumerate(PROJECTS):
            exists = "✓" if os.path.exists(proj) else "✗"
            print(f"  {i}. {exists} {proj}")

    if APPS:
        if PROJECTS:
            print("")  # Add blank line between sections
        print("⚡ APPS (examples: 'aio {0}' runs first app):".format(len(PROJECTS)))
        for i, (app_name, app_cmd) in enumerate(APPS):
            cmd_display = format_app_command(app_cmd)
            print(f"  {len(PROJECTS) + i}. {app_name} → {cmd_display}")
elif arg == 'update':
    # Explicitly update aio from git repository
    manual_update()
elif arg == 'font':
    # Font size control
    handle_font_command(sys.argv[2:])
elif arg in ('fix', 'bug', 'feat', 'auto', 'del'):
    # Prompt-based sessions: aio fix, aio bug "task", aio feat "task", aio auto, aio del
    prompts = load_prompts()
    args = sys.argv[2:]
    agent = 'l'  # Default to claude
    if args and args[0] in ('c', 'l', 'g'):
        agent, args = args[0], args[1:]
    if arg in ('fix', 'auto', 'del'):
        prompt = prompts[arg]  # autonomous modes, no task needed
        task = 'autonomous'
    else:
        task = ' '.join(args) if args else input(f"{arg}: ")
        prompt = prompts[arg].format(task=task)
    agent_name, cmd = sessions[agent]
    session_name = f"{arg}-{agent}-{datetime.now().strftime('%H%M%S')}"
    print(f"📝 {arg.upper()} [{agent_name}]: {task[:50]}{'...' if len(task) > 50 else ''}")
    create_tmux_session(session_name, os.getcwd(), f"{cmd} {shlex.quote(prompt)}")
    launch_in_new_window(session_name) if 'TMUX' in os.environ else os.execvp(sm.attach(session_name)[0], sm.attach(session_name))
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

    print(f"\nRun 'aio update' to check for and pull updates from git.")
elif arg == 'deps':
    # Install dependencies: python packages, node/npm, codex, claude, gemini
    import platform, urllib.request, tarfile, lzma
    def _which(cmd): return shutil.which(cmd) is not None
    bin_dir = os.path.expanduser('~/.local/bin')
    os.makedirs(bin_dir, exist_ok=True)
    print("📦 Installing dependencies...\n")
    # Python packages (pexpect, prompt_toolkit)
    # pkg_name -> (import_name, apt_package_name)
    pip_deps = [('pexpect', 'pexpect', 'python3-pexpect'), ('prompt_toolkit', 'prompt_toolkit', 'python3-prompt-toolkit')]
    for pkg, import_name, apt_pkg in pip_deps:
        try:
            __import__(import_name)
            print(f"✓ {pkg}")
        except ImportError:
            print(f"⬇️  {pkg}: installing...")
            installed = False
            # Try pip first
            try:
                result = sp.run([sys.executable, '-m', 'pip', 'install', '--user', pkg], capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"✓ {pkg} installed (pip)")
                    installed = True
            except: pass
            # Try apt-get (Ubuntu/Debian) - update cache first if needed
            if not installed and _which('apt-get'):
                try:
                    # Check if we need sudo
                    need_sudo = os.geteuid() != 0 if hasattr(os, 'geteuid') else False
                    apt_cmd = ['sudo', 'apt-get'] if need_sudo else ['apt-get']
                    # Try install, if fails with "Unable to locate", run update first
                    result = sp.run(apt_cmd + ['install', '-y', apt_pkg], capture_output=True, text=True)
                    if result.returncode == 0:
                        print(f"✓ {pkg} installed (apt)")
                        installed = True
                    elif 'unable to locate' in result.stderr.lower():
                        # Update package cache and retry
                        sp.run(apt_cmd + ['update'], capture_output=True, text=True)
                        result = sp.run(apt_cmd + ['install', '-y', apt_pkg], capture_output=True, text=True)
                        if result.returncode == 0:
                            print(f"✓ {pkg} installed (apt)")
                            installed = True
                except: pass
            # Try pkg (Termux)
            if not installed and _which('pkg'):
                try:
                    result = sp.run(['pkg', 'install', '-y', import_name], capture_output=True, text=True)
                    if result.returncode == 0:
                        print(f"✓ {pkg} installed (pkg)")
                        installed = True
                except: pass
            if not installed:
                print(f"✗ {pkg} - install manually: pip install {pkg} OR apt install {apt_pkg}")
    # Check tmux
    print("✓ tmux" if _which('tmux') else "⚠ tmux not found - install via: pkg install tmux (Termux) or sudo apt install tmux")
    # Node.js/npm (binary)
    node_dir = os.path.expanduser('~/.local/node')
    node_bin = os.path.join(node_dir, 'bin')
    npm_path = os.path.join(node_bin, 'npm')
    if not _which('npm') and not os.path.exists(npm_path):
        arch = 'x64' if platform.machine() in ('x86_64', 'AMD64') else 'arm64'
        url = f'https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-{arch}.tar.xz'
        print(f"⬇️  node/npm: downloading...")
        try:
            xz_path = '/tmp/node.tar.xz'
            urllib.request.urlretrieve(url, xz_path)
            with lzma.open(xz_path) as xz:
                with tarfile.open(fileobj=xz) as tar:
                    tar.extractall(os.path.expanduser('~/.local'), filter='data')
            os.rename(os.path.expanduser(f'~/.local/node-v22.11.0-linux-{arch}'), node_dir)
            os.remove(xz_path)
            # Symlink npm and node to bin_dir
            for cmd in ['node', 'npm', 'npx']:
                src, dst = os.path.join(node_bin, cmd), os.path.join(bin_dir, cmd)
                if os.path.exists(dst): os.remove(dst)
                os.symlink(src, dst)
            print("✓ node/npm installed")
        except Exception as e:
            print(f"✗ node/npm failed: {e}")
    else:
        print("✓ node/npm")
    # npm packages (codex, claude, gemini)
    npm_cmd = npm_path if os.path.exists(npm_path) else 'npm'
    npm_deps = [('codex', '@openai/codex'), ('claude', '@anthropic-ai/claude-code'), ('gemini', '@google/gemini-cli')]
    for cmd, pkg in npm_deps:
        if not _which(cmd):
            print(f"⬇️  {cmd}: installing...")
            try:
                sp.run([npm_cmd, 'install', '-g', pkg], check=True, capture_output=True)
                print(f"✓ {cmd} installed")
            except Exception as e:
                print(f"✗ {cmd} failed: {e}")
        else:
            print(f"✓ {cmd}")
    print("\n✅ Done! Restart terminal or run: export PATH=\"$HOME/.local/bin:$PATH\"")
# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL FILES SERVICE - Commented out for future activation
# Provides HTTP access to Termux local files for AI agents
# Activate with: aio files [port]
# ═══════════════════════════════════════════════════════════════════════════════
# elif arg == 'files':
#     # Local files HTTP server for agent access to Termux storage
#     import http.server
#     import socketserver
#     import threading
#     import urllib.parse
#
#     port = int(work_dir_arg) if work_dir_arg and work_dir_arg.isdigit() else 8421
#
#     # Paths accessible to agents (Termux storage locations)
#     ALLOWED_ROOTS = [
#         os.path.expanduser('~/storage/downloads'),
#         os.path.expanduser('~/storage/shared'),
#         os.path.expanduser('~/storage/dcim'),
#         os.path.expanduser('~/storage/pictures'),
#         os.path.expanduser('~/storage/music'),
#         os.path.expanduser('~/storage/movies'),
#         os.path.expanduser('~'),  # Home directory
#     ]
#
#     class LocalFilesHandler(http.server.BaseHTTPRequestHandler):
#         """HTTP handler for serving local files to AI agents."""
#
#         def log_message(self, format, *args):
#             print(f"[files] {args[0]}")
#
#         def send_cors_headers(self):
#             self.send_header('Access-Control-Allow-Origin', '*')
#             self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
#             self.send_header('Access-Control-Allow-Headers', 'Content-Type')
#
#         def do_OPTIONS(self):
#             self.send_response(200)
#             self.send_cors_headers()
#             self.end_headers()
#
#         def do_GET(self):
#             # Parse path
#             parsed = urllib.parse.urlparse(self.path)
#             path = urllib.parse.unquote(parsed.path)
#
#             # List roots at /
#             if path == '/' or path == '':
#                 self.send_response(200)
#                 self.send_header('Content-Type', 'application/json')
#                 self.send_cors_headers()
#                 self.end_headers()
#                 roots = [{'path': r, 'name': os.path.basename(r) or 'home', 'exists': os.path.exists(r)} for r in ALLOWED_ROOTS]
#                 self.wfile.write(json.dumps({'roots': roots, 'usage': 'GET /path/to/file'}).encode())
#                 return
#
#             # Resolve full path
#             full_path = None
#             for root in ALLOWED_ROOTS:
#                 if path.startswith('/' + os.path.basename(root)):
#                     # Path starts with root name (e.g., /downloads/file.txt)
#                     rel = path[len('/' + os.path.basename(root)):]
#                     candidate = os.path.join(root, rel.lstrip('/'))
#                     if os.path.exists(candidate):
#                         full_path = candidate
#                         break
#                 elif os.path.exists(root + path):
#                     full_path = root + path
#                     break
#
#             # Also try absolute path if within allowed roots
#             if not full_path and path.startswith('/'):
#                 abs_path = path
#                 for root in ALLOWED_ROOTS:
#                     if abs_path.startswith(root) and os.path.exists(abs_path):
#                         full_path = abs_path
#                         break
#
#             if not full_path or not os.path.exists(full_path):
#                 self.send_response(404)
#                 self.send_cors_headers()
#                 self.end_headers()
#                 self.wfile.write(b'File not found')
#                 return
#
#             # Security: ensure path is within allowed roots
#             real_path = os.path.realpath(full_path)
#             if not any(real_path.startswith(os.path.realpath(r)) for r in ALLOWED_ROOTS):
#                 self.send_response(403)
#                 self.send_cors_headers()
#                 self.end_headers()
#                 self.wfile.write(b'Access denied')
#                 return
#
#             # Directory listing
#             if os.path.isdir(full_path):
#                 self.send_response(200)
#                 self.send_header('Content-Type', 'application/json')
#                 self.send_cors_headers()
#                 self.end_headers()
#                 entries = []
#                 for name in sorted(os.listdir(full_path)):
#                     entry_path = os.path.join(full_path, name)
#                     entries.append({
#                         'name': name,
#                         'type': 'dir' if os.path.isdir(entry_path) else 'file',
#                         'size': os.path.getsize(entry_path) if os.path.isfile(entry_path) else None
#                     })
#                 self.wfile.write(json.dumps({'path': path, 'entries': entries}).encode())
#                 return
#
#             # Serve file
#             try:
#                 with open(full_path, 'rb') as f:
#                     content = f.read()
#                 self.send_response(200)
#                 # Guess content type
#                 ext = os.path.splitext(full_path)[1].lower()
#                 content_types = {
#                     '.txt': 'text/plain', '.md': 'text/markdown', '.json': 'application/json',
#                     '.py': 'text/x-python', '.js': 'text/javascript', '.html': 'text/html',
#                     '.css': 'text/css', '.xml': 'application/xml', '.pdf': 'application/pdf',
#                     '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
#                     '.gif': 'image/gif', '.svg': 'image/svg+xml', '.mp3': 'audio/mpeg',
#                     '.mp4': 'video/mp4', '.epub': 'application/epub+zip',
#                 }
#                 self.send_header('Content-Type', content_types.get(ext, 'application/octet-stream'))
#                 self.send_header('Content-Length', str(len(content)))
#                 self.send_cors_headers()
#                 self.end_headers()
#                 self.wfile.write(content)
#             except Exception as e:
#                 self.send_response(500)
#                 self.send_cors_headers()
#                 self.end_headers()
#                 self.wfile.write(f'Error: {e}'.encode())
#
#     print(f"📂 Local Files Server")
#     print(f"═══════════════════════════════════════════════════")
#     print(f"URL: http://localhost:{port}")
#     print(f"")
#     print(f"Accessible paths:")
#     for root in ALLOWED_ROOTS:
#         exists = "✓" if os.path.exists(root) else "✗"
#         print(f"  {exists} {root}")
#     print(f"")
#     print(f"Usage for agents:")
#     print(f"  curl http://localhost:{port}/downloads/")
#     print(f"  curl http://localhost:{port}/downloads/file.txt")
#     print(f"")
#     print(f"Press Ctrl+C to stop")
#     print(f"═══════════════════════════════════════════════════")
#
#     with socketserver.TCPServer(("", port), LocalFilesHandler) as httpd:
#         try:
#             httpd.serve_forever()
#         except KeyboardInterrupt:
#             print("\n✓ Server stopped")
#             sys.exit(0)
# ═══════════════════════════════════════════════════════════════════════════════

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
    # Run multiple agents in ONE tmux session with tabs, each in its own worktree
    # Structure: WORKTREES_DIR/repo_name/run_id/attempt_N
    import json, hashlib

    if work_dir_arg and work_dir_arg.isdigit():
        project_path = PROJECTS[int(work_dir_arg)] if int(work_dir_arg) < len(PROJECTS) else None
        if not project_path:
            print(f"✗ Invalid project index"); sys.exit(1)
        start_parse_at = 3
    else:
        project_path = os.getcwd()
        start_parse_at = 2

    agent_specs, task, used_default = parse_agent_specs_and_prompt(sys.argv, start_parse_at)
    if not agent_specs:
        spec = input("Agent specs (e.g. c:3 or c:2 l:1): ").strip()
        if not spec: sys.exit(1)
        agent_specs, task, used_default = parse_agent_specs_and_prompt([''] + spec.split(), 1)
    if used_default:
        task = input_box("", "Task (Ctrl+D to run)").strip()
        if not task: sys.exit(1)

    # Wrap task with feat prompt template
    prompts = load_prompts()
    prompt = prompts['feat'].format(task=task)

    total = sum(count for _, count in agent_specs)
    repo_name = os.path.basename(project_path)
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    session_name = f"{repo_name}-{run_id}"

    # Create run directory: WORKTREES_DIR/repo_name/run_id/candidates/
    run_dir = os.path.join(WORKTREES_DIR, repo_name, run_id)
    candidates_dir = os.path.join(run_dir, "candidates")
    os.makedirs(candidates_dir, exist_ok=True)

    # Save to JSON and DB (store task for display, prompt is the full formatted version)
    run_info = {"task": task, "prompt": prompt, "agents": [f"{k}:{c}" for k, c in agent_specs], "created": run_id, "repo": project_path}
    with open(os.path.join(run_dir, "run.json"), "w") as f:
        json.dump(run_info, f, indent=2)

    with WALManager(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO multi_runs VALUES (?, ?, ?, ?, 'running', CURRENT_TIMESTAMP, NULL)",
                    (run_id, project_path, task, json.dumps([f"{k}:{c}" for k, c in agent_specs])))
        conn.commit()

    print(f"🚀 Starting {total} agents + reviewer in {repo_name}/{run_id}...")
    escaped_prompt = shlex.quote(prompt)
    env = get_noninteractive_git_env()
    launched = []
    agent_num = {}  # Track count per agent type for naming

    first_window = True
    for agent_key, count in agent_specs:
        base_name, base_cmd = sessions.get(agent_key, (None, None))
        if not base_name: continue

        for i in range(count):
            # Better window name: codex-1, claude-2, etc.
            agent_num[base_name] = agent_num.get(base_name, 0) + 1
            window_name = f"{base_name}-{agent_num[base_name]}"
            attempt_name = f"{agent_key}{i}"
            # Put worktree in candidates folder: repo/runid/candidates/c0
            wt_path = os.path.join(candidates_dir, attempt_name)

            # Create git worktree
            branch_name = f"wt-{repo_name}-{run_id}-{attempt_name}"
            sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', branch_name, wt_path], capture_output=True, env=env)
            if not os.path.exists(wt_path): continue

            signal_name = f"{session_name}-{window_name}"
            # Fallback 1: Signal on agent exit (handles crashes, user quit, completion)
            exit_signal = f'; tmux wait-for -S {signal_name}'
            full_cmd = f'{base_cmd} {escaped_prompt}{exit_signal}'
            if first_window:
                sp.run(['tmux', 'new-session', '-d', '-s', session_name, '-n', window_name, '-c', wt_path, full_cmd], env=env)
                first_window = False
            else:
                sp.run(['tmux', 'new-window', '-t', session_name, '-n', window_name, '-c', wt_path, full_cmd], env=env)

            # Split: agent left, bash right
            sp.run(['tmux', 'split-window', '-h', '-t', f'{session_name}:{window_name}', '-c', wt_path], env=env)
            sp.run(['tmux', 'select-pane', '-t', f'{session_name}:{window_name}.0'], env=env)

            # Fallback 2: Prompt detection (idle agent) - signals if prompt AND (>20 lines OR >10s elapsed)
            detector = f'''sh -c 's=$(date +%s);n=0;while IFS= read -r l;do n=$((n+1));e=$(($(date +%s)-s));echo "$l"|sed "s/$(printf "\\033")\\[[0-9;]*[a-zA-Z]//g"|grep -q "[›>] "&&[ $n -gt 20 -o $e -gt 10 ]&&tmux wait-for -S {signal_name}&&exit 0;done' '''
            sp.run(['tmux', 'pipe-pane', '-t', f'{session_name}:{window_name}.0', detector], env=env)

            # Fallback 3: Inactivity timeout (30 min) - handles stuck agents
            sp.run(['tmux', 'set-option', '-t', f'{session_name}:{window_name}', 'monitor-silence', '1800'], env=env)
            sp.run(['tmux', 'set-hook', '-t', f'{session_name}:{window_name}', 'alert-silence',
                    f'run-shell "tmux wait-for -S {signal_name}"'], env=env)

            launched.append((window_name, base_name, wt_path))
            print(f"✓ {window_name}")

    if not launched:
        print("✗ No agents created"); sys.exit(1)

    # Build reviewer prompt with context
    agents_str = ", ".join(f"{k}:{c}" for k, c in agent_specs)
    dirs_str = ", ".join(os.path.basename(p) for _, _, p in launched)
    prompt_template = get_prompt('reviewer') or "Review {DIRS} for: {TASK}"
    REVIEWER_PROMPT = prompt_template.format(TASK=prompt, AGENTS=agents_str, DIRS=dirs_str)

    # Add reviewer window (event-driven: waits for all agent signals, then auto-starts)
    # Review runs in candidates/ folder so it can see all candidate dirs
    wait_cmds = '; '.join(f'echo "  waiting for {w}..."; tmux wait-for {session_name}-{w}; echo "  ✓ {w} done"' for w, _, _ in launched)
    wait_script = f'''echo "⏳ Waiting for agents to complete..."
echo "   Run 'aio r' to force review now"
echo ""
{wait_cmds}
echo ""
echo "✓ All agents done. Starting review..."
claude --dangerously-skip-permissions {shlex.quote(REVIEWER_PROMPT)}'''
    sp.run(['tmux', 'new-window', '-t', session_name, '-n', '📋review', '-c', candidates_dir, f'bash -c {shlex.quote(wait_script)}'], env=env)
    sp.run(['tmux', 'split-window', '-h', '-t', f'{session_name}:📋review', '-c', candidates_dir], env=env)
    print("✓ 📋review (auto-starts when agents finish)")

    # Select first agent window
    sp.run(['tmux', 'select-window', '-t', f'{session_name}:{launched[0][0]}'], capture_output=True)
    ensure_tmux_options()
    sp.run(['tmux', 'set-option', '-t', session_name, 'status-right', 'Ctrl+Q:Detach | 📋review auto-starts when done'], capture_output=True)

    print(f"\n✓ Session '{session_name}': {len(launched)} agents + 📋review (auto-starts)")
    print(f"   Use 'aio attach' to reconnect")

    if "TMUX" in os.environ:
        print(f"   Attach: tmux switch-client -t {session_name}")
    else:
        os.execvp('tmux', ['tmux', 'attach', '-t', session_name])
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
                # Create unique worktree name with project index for uniqueness
                import time
                date_str = datetime.now().strftime('%Y%m%d')
                time_str = datetime.now().strftime('%H%M%S')
                # Include project index to guarantee uniqueness across projects
                worktree_name = f"{base_name}-{date_str}-{time_str}-all-p{project_idx}-{instance_num}"

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
                # Note: escaped_prompt already has quotes from shlex.quote()
                full_cmd = f'{base_cmd} {escaped_prompt}'

                # Create tmux session in worktree with prompt already included
                # IMPORTANT: Use clean environment to prevent GUI dialogs in the agent session
                # Use the full worktree name (with project prefix) as session name
                session_name = os.path.basename(worktree_path)
                env = get_noninteractive_git_env()
                result = create_tmux_session(session_name, worktree_path, full_cmd, env=env)
                if result.returncode != 0:
                    print(f"✗ Failed to create tmux session: {result.stderr}")
                    print(f"  Command was: tmux new-session -d -s {session_name} -c {worktree_path} {full_cmd[:100]}...")

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
elif arg == 'attach':
    # Attach to session associated with current directory or run_id
    run_id = work_dir_arg
    cwd = os.getcwd()

    # If in a worktree, find its session
    if WORKTREES_DIR in cwd:
        parts = cwd.replace(WORKTREES_DIR + '/', '').split('/')
        if len(parts) >= 2:
            repo_name, run_id = parts[0], parts[1]
            session_name = f"{repo_name}-{run_id}"
            if sm.has_session(session_name):
                print(f"Attaching to {session_name}...")
                if "TMUX" in os.environ:
                    os.execvp('tmux', ['tmux', 'switch-client', '-t', session_name])
                else:
                    os.execvp('tmux', ['tmux', 'attach', '-t', session_name])

    # Otherwise list recent sessions
    with WALManager(DB_PATH) as conn:
        runs = conn.execute("SELECT id, repo FROM multi_runs ORDER BY created_at DESC LIMIT 10").fetchall()
    if runs:
        print("Recent sessions:")
        for i, (rid, repo) in enumerate(runs):
            sname = f"{os.path.basename(repo)}-{rid}"
            status = "●" if sm.has_session(sname) else "○"
            print(f"  {i}. {status} {sname}")
        choice = input("Select #: ").strip()
        if choice.isdigit() and int(choice) < len(runs):
            rid, repo = runs[int(choice)]
            session_name = f"{os.path.basename(repo)}-{rid}"
            if "TMUX" in os.environ:
                os.execvp('tmux', ['tmux', 'switch-client', '-t', session_name])
            else:
                os.execvp('tmux', ['tmux', 'attach', '-t', session_name])
    print("No session found")

elif arg == 'killall':
    # Kill all tmux sessions (except current if inside tmux)
    sessions_out = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True)
    if sessions_out.returncode != 0:
        print("No tmux sessions running"); sys.exit(0)
    all_sessions = [s for s in sessions_out.stdout.strip().split('\n') if s]
    if not all_sessions:
        print("No tmux sessions running"); sys.exit(0)

    current = os.environ.get('TMUX', '').split(',')[0].split('/')[-1] if 'TMUX' in os.environ else None
    if current:
        # Get current session name
        current = sp.run(['tmux', 'display-message', '-p', '#{session_name}'], capture_output=True, text=True).stdout.strip()
        to_kill = [s for s in all_sessions if s != current]
        msg = f"Kill {len(to_kill)} sessions (keeping '{current}')?"
    else:
        to_kill = all_sessions
        msg = f"Kill all {len(to_kill)} tmux sessions?"

    if not to_kill:
        print("No other sessions to kill"); sys.exit(0)

    print(f"Sessions to kill: {', '.join(to_kill)}")
    if input(f"{msg} (y/n): ").strip().lower() in ['y', 'yes']:
        for s in to_kill:
            sp.run(['tmux', 'kill-session', '-t', s], capture_output=True)
        print(f"✓ Killed {len(to_kill)} sessions")
    else:
        print("Cancelled")

elif arg == 'prompt':
    # Edit prompts: aio prompt [name]
    prompts = load_prompts()
    name = work_dir_arg or 'feat'
    if name not in prompts:
        print(f"Available: {', '.join(prompts.keys())}")
        sys.exit(1)
    new_val = input_box(prompts[name], f"Edit '{name}' (Ctrl+D to save)")
    if new_val != prompts[name]:
        prompts[name] = new_val
        os.makedirs(os.path.dirname(PROMPTS_FILE), exist_ok=True)
        with open(PROMPTS_FILE, 'w') as f: json.dump(prompts, f, indent=2)
        print(f"✓ Saved '{name}' prompt")
    else:
        print("No changes")

elif arg == 'r' or arg == 'review':
    # Review mode: add reviewer window to existing session
    # 'aio r' = force review on most recent run (no prompt)
    # 'aio review' = interactive selection
    import json
    force_latest = (arg == 'r')

    # Find run to review
    if work_dir_arg:
        run_id = work_dir_arg
    else:
        with WALManager(DB_PATH) as conn:
            runs = conn.execute("SELECT id, repo, prompt, status, created_at FROM multi_runs ORDER BY created_at DESC LIMIT 10").fetchall()
        if not runs:
            print("No runs to review. Use 'aio multi' first.")
            sys.exit(0)
        if force_latest:
            # Auto-select most recent
            run_id = runs[0][0]
            print(f"📋 Force reviewing: {runs[0][2][:50]}...")
        else:
            print("Recent runs:")
            for i, (rid, repo, prompt, status, created_at) in enumerate(runs):
                elapsed = ""
                if created_at:
                    try:
                        mins = int((datetime.now() - datetime.fromisoformat(created_at)).total_seconds() / 60)
                        elapsed = f"{mins}m" if mins < 60 else f"{mins//60}h{mins%60}m"
                    except: pass
                print(f"  {i}. [{status}] {elapsed:>5} {rid} - {os.path.basename(repo)}: {prompt[:40]}...")
            choice = input("Select #: ").strip()
            run_id = runs[int(choice)][0] if choice.isdigit() and int(choice) < len(runs) else choice

    # Find run directory: WORKTREES_DIR/repo/run_id/
    # Worktrees are in: WORKTREES_DIR/repo/run_id/candidates/c0, l0, etc.
    run_dir = None
    repo_name = None
    candidates_dir = None

    if os.path.exists(WORKTREES_DIR):
        for rd in os.listdir(WORKTREES_DIR):
            candidate = os.path.join(WORKTREES_DIR, rd, run_id)
            if os.path.isdir(candidate):
                run_dir = candidate
                repo_name = rd
                candidates_dir = os.path.join(run_dir, "candidates")
                break

    if not run_dir:
        print(f"✗ Run not found: {run_id}")
        sys.exit(1)

    # Load run context and build reviewer prompt
    task, agents = "unknown", "unknown"
    run_json = os.path.join(run_dir, "run.json")
    if os.path.exists(run_json):
        with open(run_json) as f:
            info = json.load(f)
            task = info.get("task") or info.get("prompt", "unknown")
            agents = ", ".join(info.get("agents", []))

    # List candidate dirs (c0, l0, etc.)
    candidate_names = []
    if candidates_dir and os.path.exists(candidates_dir):
        candidate_names = [d for d in os.listdir(candidates_dir)
                         if os.path.isdir(os.path.join(candidates_dir, d))]
    dirs = ", ".join(candidate_names)

    prompt_template = get_prompt('reviewer') or "Review the code in {DIRS} for task: {TASK}"
    REVIEWER_PROMPT = prompt_template.format(TASK=task, AGENTS=agents, DIRS=dirs)
    print(f"📋 Reviewing: {task[:60]}...")
    print(f"   Agents: {agents} | Dirs: {dirs}")

    # Session name matches multi command
    session_name = f"{repo_name}-{run_id}"
    env = get_noninteractive_git_env()

    # Working dir: candidates folder (contains c0, l0, etc.)
    review_cwd = candidates_dir if candidates_dir and os.path.exists(candidates_dir) else run_dir

    # Add reviewer window to existing session (or create if doesn't exist)
    reviewer_cmd = f"claude --dangerously-skip-permissions {shlex.quote(REVIEWER_PROMPT)}"
    if sm.has_session(session_name):
        # Add reviewer as new window
        sp.run(['tmux', 'new-window', '-t', session_name, '-n', 'reviewer', '-c', review_cwd, reviewer_cmd], env=env)
    else:
        # Create session with reviewer
        sp.run(['tmux', 'new-session', '-d', '-s', session_name, '-n', 'reviewer', '-c', review_cwd, reviewer_cmd], env=env)

    # Split reviewer window: agent left, bash right
    sp.run(['tmux', 'split-window', '-h', '-t', f'{session_name}:reviewer', '-c', review_cwd], env=env)
    sp.run(['tmux', 'select-window', '-t', f'{session_name}:reviewer'], capture_output=True)

    ensure_tmux_options()
    print(f"✓ Added reviewer to session '{session_name}'")
    print(f"   Use 'aio attach' to reconnect")

    # Attach
    if "TMUX" in os.environ:
        os.execvp('tmux', ['tmux', 'switch-client', '-t', session_name])
    else:
        os.execvp('tmux', ['tmux', 'attach', '-t', session_name])
elif arg == 'cleanup':
    # Delete all worktrees - simple approach: rm -rf + git worktree prune
    import shutil

    worktrees = []
    if os.path.exists(WORKTREES_DIR):
        worktrees = [d for d in os.listdir(WORKTREES_DIR)
                     if os.path.isdir(os.path.join(WORKTREES_DIR, d))]

    # Check if there's anything to clean (directories or db entries)
    with WALManager(DB_PATH) as conn:
        db_count = conn.execute("SELECT COUNT(*) FROM multi_runs").fetchone()[0]

    if not worktrees and db_count == 0:
        print("Nothing to clean")
        sys.exit(0)

    if worktrees:
        print(f"Found {len(worktrees)} directories:\n")
        for wt in worktrees:
            print(f"  • {wt}")
    if db_count:
        print(f"\n{db_count} run entries in database")

    print(f"\n⚠️  This will:")
    if worktrees:
        print(f"   • Delete {len(worktrees)} directories")
    print(f"   • Prune stale worktree refs from projects")
    if db_count:
        print(f"   • Clear {db_count} run history entries")

    skip_confirm = '--yes' in sys.argv or '-y' in sys.argv
    if not skip_confirm:
        if input("\nContinue? (y/n): ").strip().lower() not in ['y', 'yes']:
            print("✗ Cancelled"); sys.exit(0)

    # Step 1: Delete all directories
    deleted = 0
    if worktrees:
        print("\n🗑️  Deleting directories...")
        for wt in worktrees:
            path = os.path.join(WORKTREES_DIR, wt)
            try:
                shutil.rmtree(path)
                print(f"  ✓ {wt}")
                deleted += 1
            except Exception as e:
                print(f"  ✗ {wt}: {e}")

    # Step 2: Prune stale worktree refs from all known projects
    print("\n🧹 Pruning stale refs from projects...")
    for proj in PROJECTS:
        if os.path.exists(proj):
            result = sp.run(['git', '-C', proj, 'worktree', 'prune'], capture_output=True)
            if result.returncode == 0:
                print(f"  ✓ {os.path.basename(proj)}")

    # Step 3: Clear multi_runs database table
    with WALManager(DB_PATH) as conn:
        conn.execute("DELETE FROM multi_runs")
        conn.commit()
    print("  ✓ Cleared run history")

    print(f"\n✓ Cleanup complete" + (f" ({deleted} directories)" if deleted else ""))
elif arg == 'p':
    if PROJECTS:
        print("📁 PROJECTS:")
        for i, proj in enumerate(PROJECTS):
            exists = "✓" if os.path.exists(proj) else "✗"
            print(f"  {i}. {exists} {proj}")

    if APPS:
        if PROJECTS:
            print("")  # Add blank line between sections
        print("⚡ APPS:")
        for i, (app_name, app_cmd) in enumerate(APPS):
            cmd_display = format_app_command(app_cmd)
            print(f"  {len(PROJECTS) + i}. {app_name} → {cmd_display}")
elif arg == 'app' or arg == 'apps':
    # App management commands
    subcommand = work_dir_arg

    if not subcommand or subcommand == 'list':
        # List all apps
        if not APPS:
            print("No apps configured yet.")
            print("\n💡 Add your first app:")
            print("   aio app add myapp 'echo Hello World'")
        else:
            print("⚡ CONFIGURED APPS:")
            for i, (app_name, app_cmd) in enumerate(APPS):
                cmd_display = format_app_command(app_cmd)
                app_idx = len(PROJECTS) + i
                print(f"  [{app_idx}] {app_name} → {cmd_display}")
            print(f"\n💡 Commands:")
            print(f"   aio app add <name> [command]  - Add new app")
            print(f"   aio app edit <#|name>         - Edit app command")
            print(f"   aio app rm <#|name>           - Remove app")
            print(f"   aio <#>                       - Run app by number")

    elif subcommand == 'add':
        # Check for --global flag
        is_global = '--global' in sys.argv
        args = [arg for arg in sys.argv[3:] if arg != '--global']

        if not args:
            print("✗ Usage: aio app add <name> <command>")
            print("        aio app add <command>  (prompts for name)")
            sys.exit(1)

        # Check if first arg looks like a command (starts with common interpreters)
        first_arg = args[0]
        command_starters = ['python', 'python3', 'node', 'npm', 'ruby', 'perl', 'java', 'go', 'sh', 'bash']

        if first_arg in command_starters or len(args) == 1:
            # Treat whole thing as command, prompt for name
            app_command = ' '.join(args)
            print(f"Command: {format_app_command(app_command)}")
            app_name = input("Name for this app: ").strip()
            if not app_name:
                print("✗ Cancelled")
                sys.exit(1)
        else:
            # First arg is name, rest is command
            app_name = args[0]
            app_command = ' '.join(args[1:]) if len(args) > 1 else None

            if not app_command:
                print(f"Adding app: {app_name}")
                app_command = input("Command: ").strip()
                if not app_command:
                    print("✗ Cancelled")
                    sys.exit(1)

        # Clean brackets if present
        if app_command.startswith('[') and app_command.endswith(']'):
            app_command = app_command[1:-1]

        # Add directory context (unless --global or already has cd)
        current_dir = os.getcwd()
        home_dir = os.path.expanduser('~')

        if not is_global and current_dir != home_dir and not app_command.startswith('cd '):
            rel_path = current_dir.replace(home_dir, '~') if current_dir.startswith(home_dir) else current_dir
            app_command = f"cd {rel_path} && {app_command}"
            print(f"📍 Added: {rel_path}")

        # Handle duplicates
        existing = {name.lower(): name for name, _ in APPS}
        if app_name.lower() in existing:
            print(f"✗ '{existing[app_name.lower()]}' exists. (1) rename (2) update (3) cancel")
            choice = input("> ").strip()
            if choice == '1':
                app_name = input("New name: ").strip()
                if not app_name:
                    sys.exit(1)
            elif choice == '2':
                with WALManager(DB_PATH) as conn:
                    conn.execute("UPDATE apps SET command = ? WHERE LOWER(name) = LOWER(?)",
                               (app_command, app_name))
                print(f"✓ Updated: {app_name}")
                sys.exit(0)
            else:
                sys.exit(1)

        # Add the app
        success, message = add_app(app_name, app_command)
        if success:
            print(f"✓ {message}")
            auto_backup_check()  # Backup after database modification
            # Show updated list
            APPS_NEW = load_apps()
            for i, (name, cmd) in enumerate(APPS_NEW):
                print(f"  [{len(PROJECTS) + i}] {name} → {format_app_command(cmd)}")
        else:
            print(f"✗ {message}")
            sys.exit(1)

    elif subcommand == 'edit':
        # Get app identifier (number or name)
        app_id = sys.argv[3] if len(sys.argv) > 3 else None

        if not app_id:
            print("✗ Usage: aio app edit <#|name>")
            sys.exit(1)

        # Find the app
        app_index = None
        app_name = None
        app_command = None

        if app_id.isdigit():
            # User provided global index
            idx = int(app_id)
            app_idx = idx - len(PROJECTS)
            if 0 <= app_idx < len(APPS):
                app_index = app_idx
                app_name, app_command = APPS[app_idx]
        else:
            # User provided name - search for it
            for i, (name, cmd) in enumerate(APPS):
                if name.lower() == app_id.lower():
                    app_index = i
                    app_name = name
                    app_command = cmd
                    break

        if app_index is None:
            print(f"✗ App not found: {app_id}")
            sys.exit(1)

        # Show current command and prompt for new one
        print(f"Editing app: {app_name}")
        print(f"Current command: {format_app_command(app_command)}")
        print("\nEnter new command (or press Enter to keep current):")
        new_command = input("> ").strip()

        if new_command:
            # Update the app in database
            with WALManager(DB_PATH) as conn:
                with conn:
                    conn.execute("UPDATE apps SET command = ? WHERE name = ?",
                               (new_command, app_name))
            print(f"✓ Updated app: {app_name}")
            print(f"   New command: {format_app_command(new_command)}")
        else:
            print("✗ No changes made")

    elif subcommand == 'rm' or subcommand == 'remove' or subcommand == 'delete':
        # Get app identifier (number or name)
        app_id = sys.argv[3] if len(sys.argv) > 3 else None

        if not app_id:
            print("✗ Usage: aio app rm <#|name>")
            sys.exit(1)

        # Find the app
        app_index = None
        app_name = None

        if app_id.isdigit():
            # User provided global index
            idx = int(app_id)
            app_idx = idx - len(PROJECTS)
            if 0 <= app_idx < len(APPS):
                app_index = app_idx
                app_name = APPS[app_idx][0]
        else:
            # User provided name - search for it
            for i, (name, cmd) in enumerate(APPS):
                if name.lower() == app_id.lower():
                    app_index = i
                    app_name = name
                    break

        if app_index is None:
            print(f"✗ App not found: {app_id}")
            sys.exit(1)

        # Confirm deletion
        print(f"Delete app '{app_name}'? (y/n):")
        response = input("> ").strip().lower()

        if response in ['y', 'yes']:
            success, message = remove_app(app_index)
            if success:
                print(f"✓ {message}")
                auto_backup_check()  # Backup after database modification
            else:
                print(f"✗ {message}")
        else:
            print("✗ Cancelled")
    else:
        print(f"✗ Unknown app command: {subcommand}")
        print("\nAvailable commands:")
        print("  aio app         - List all apps")
        print("  aio app add     - Add a new app")
        print("  aio app edit    - Edit an app")
        print("  aio app rm      - Remove an app")
elif arg == 'add':
    # Add a project to saved list
    if work_dir_arg:
        path = work_dir_arg
    else:
        path = os.getcwd()

    success, message = add_project(path)
    if success:
        print(f"✓ {message}")
        auto_backup_check()  # Backup after database modification
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

    # Load current projects and apps to determine which to remove
    current_projects = load_projects()
    current_apps = load_apps()

    # Check if index is for a project or an app
    if index < len(current_projects):
        # Remove project
        success, message = remove_project(index)
        item_type = "project"
    elif index < len(current_projects) + len(current_apps):
        # Remove app (adjust index)
        app_index = index - len(current_projects)
        success, message = remove_app(app_index)
        item_type = "app"
    else:
        print(f"✗ Invalid index: {index}")
        sys.exit(1)

    if success:
        print(f"✓ {message}")
        auto_backup_check()  # Backup after database modification
        print(f"\nUpdated {item_type} list:")
        # Reload and display projects or apps
        if item_type == "project":
            updated_projects = load_projects()
            for i, proj in enumerate(updated_projects):
                exists = "✓" if os.path.exists(proj) else "✗"
                print(f"  {i}. {exists} {proj}")
        else:
            updated_apps = load_apps()
            offset = len(load_projects())
            for i, (name, cmd) in enumerate(updated_apps):
                print(f"  {i + offset}. {name}: {cmd}")
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
        auto_backup_check()  # Backup after database modification
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
        auto_backup_check()  # Backup after database modification
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

    # Auto-configure git user from GitHub if needed
    ensure_git_config()

    # Check if git repo
    result = sp.run(['git', '-C', cwd, 'rev-parse', '--git-dir'], capture_output=True, text=True)
    if result.returncode != 0:
        # Auto-fix stale .git files pointing to non-existent worktrees
        if '.git/worktrees/' in result.stderr:
            stale = sp.run(f"find {cwd} -name .git -type f 2>/dev/null | xargs grep -l 'worktrees/worktree[0-9]' 2>/dev/null",
                          shell=True, capture_output=True, text=True).stdout.strip().split('\n')
            stale = [f for f in stale if f]
            if stale and input(f"⚠️  Found {len(stale)} stale .git files. Remove? (y/n): ").strip().lower() in ['y', 'yes']:
                for f in stale:
                    os.remove(f)
                print(f"✓ Removed. Continuing...")
                result = sp.run(['git', '-C', cwd, 'rev-parse', '--git-dir'], capture_output=True, text=True)
        if result.returncode != 0:
            print("✗ Not a git repository")
            sys.exit(1)

    # Check if we're in a worktree
    git_dir = result.stdout.strip()
    is_worktree = '.git/worktrees/' in git_dir or cwd.startswith(WORKTREES_DIR)

    # Get commit message (join all remaining args - supports both quoted and unquoted)
    remaining_args = [a for a in sys.argv[2:] if a not in ['--yes', '-y']]
    commit_msg = ' '.join(remaining_args) if remaining_args else f"Update {os.path.basename(cwd)}"

    if is_worktree:
        # We're in a worktree
        worktree_name = os.path.basename(cwd)
        project_path = get_project_for_worktree(cwd)

        if not project_path:
            print(f"✗ Could not determine main project for worktree: {worktree_name}")
            print(f"  Worktree: {cwd}")
            sys.exit(1)

        # Get the current branch name in worktree
        result = sp.run(['git', '-C', cwd, 'branch', '--show-current'],
                        capture_output=True, text=True)
        worktree_branch = result.stdout.strip()

        # Show options
        print(f"\n📍 Worktree: {worktree_name}")
        print(f"   Branch: {worktree_branch}")
        print(f"   Project: {project_path}")
        print(f"   Message: {commit_msg}")

        skip_confirm = '--yes' in sys.argv or '-y' in sys.argv
        push_to_main = True  # default

        if not skip_confirm:
            print(f"\nPush to:")
            print(f"  1. main (merge & push to main, optionally delete worktree)")
            print(f"  2. branch (push to {worktree_branch} only)")
            choice = input("Choice [1]: ").strip()
            if choice == '2':
                push_to_main = False
            elif choice and choice != '1':
                print("✗ Cancelled")
                sys.exit(0)

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
            if '.git/worktrees/' in error_msg:
                stale = sp.run(f"find {cwd} -name .git -type f 2>/dev/null | xargs grep -l 'worktrees/worktree[0-9]' 2>/dev/null",
                              shell=True, capture_output=True, text=True).stdout.strip().split('\n')
                stale = [f for f in stale if f]
                if stale and input(f"⚠️  Found {len(stale)} stale .git files. Remove? (y/n): ").strip().lower() in ['y', 'yes']:
                    for f in stale:
                        os.remove(f)
                    print(f"✓ Removed {len(stale)} stale .git files. Run 'aio push' again.")
                    sys.exit(0)
            print(f"✗ Commit failed: {error_msg}")
            sys.exit(1)

        if push_to_main:
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
                if 'rejected' in error_msg and 'non-fast-forward' in error_msg:
                    print(f"⚠️  Push rejected - remote has diverged. Force pushing...")
                    result = sp.run(['git', '-C', project_path, 'push', '--force-with-lease', 'origin', main_branch],
                                    capture_output=True, text=True, env=env)
                    if result.returncode == 0:
                        print(f"✓ Force pushed to {main_branch} (remote was overwritten)")
                    else:
                        print(f"✗ Force push failed: {result.stderr.strip()}")
                        sys.exit(1)
                else:
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
        else:
            # Push to branch only
            env = get_noninteractive_git_env()
            result = sp.run(['git', '-C', cwd, 'push', '-u', 'origin', worktree_branch],
                            capture_output=True, text=True, env=env)
            if result.returncode == 0:
                print(f"✓ Pushed to branch: {worktree_branch}")
            else:
                print(f"✗ Push failed: {result.stderr.strip()}")
                sys.exit(1)
            sys.exit(0)  # Done - don't ask about deleting worktree

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
        # Normal repo - always push to main branch
        # Get current branch
        result = sp.run(['git', '-C', cwd, 'branch', '--show-current'],
                        capture_output=True, text=True)
        current_branch = result.stdout.strip()

        # Detect main branch name
        result = sp.run(['git', '-C', cwd, 'symbolic-ref', 'refs/remotes/origin/HEAD'],
                        capture_output=True, text=True)
        if result.returncode == 0:
            main_branch = result.stdout.strip().replace('refs/remotes/origin/', '')
        else:
            result = sp.run(['git', '-C', cwd, 'rev-parse', '--verify', 'main'],
                           capture_output=True)
            main_branch = 'main' if result.returncode == 0 else 'master'

        # Add all changes
        sp.run(['git', '-C', cwd, 'add', '-A'])

        # Commit
        result = sp.run(['git', '-C', cwd, 'commit', '-m', commit_msg],
                        capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Committed: {commit_msg}")
        elif 'nothing to commit' in result.stdout:
            # Check if user provided a custom message (not the default)
            if work_dir_arg:  # User provided a message
                # Create empty clarification commit
                result = sp.run(['git', '-C', cwd, 'commit', '--allow-empty', '-m', commit_msg],
                                capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"✓ Created clarification commit: {commit_msg}")
                    # Continue to push below
                else:
                    print("ℹ No changes to send")
                    sys.exit(0)
            else:
                print("ℹ No changes to send")
                sys.exit(0)
        elif 'no changes added to commit' in result.stdout:
            print("ℹ No changes to send")
            print("  (Some files may be ignored or in submodules)")
            sys.exit(0)
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            if '.git/worktrees/' in error_msg:
                # Find and remove stale .git files in subdirectories pointing to bad worktrees
                stale = sp.run(f"find {cwd} -name .git -type f 2>/dev/null | xargs grep -l 'worktrees/worktree[0-9]' 2>/dev/null",
                              shell=True, capture_output=True, text=True).stdout.strip().split('\n')
                stale = [f for f in stale if f]
                if stale and input(f"⚠️  Found {len(stale)} stale .git files. Remove? (y/n): ").strip().lower() in ['y', 'yes']:
                    for f in stale:
                        os.remove(f)
                    print(f"✓ Removed {len(stale)} stale .git files. Run 'aio push' again.")
                    sys.exit(0)
            print(f"✗ Commit failed: {error_msg}")
            sys.exit(1)

        # If we're not on main, switch to it and merge current branch
        if current_branch != main_branch:
            print(f"→ Switching to {main_branch} and merging {current_branch}...")

            # Switch to main branch
            result = sp.run(['git', '-C', cwd, 'checkout', main_branch],
                            capture_output=True, text=True)
            if result.returncode != 0:
                print(f"✗ Failed to switch to {main_branch}: {result.stderr.strip()}")
                sys.exit(1)

            # Merge current branch into main
            result = sp.run(['git', '-C', cwd, 'merge', current_branch, '--no-edit', '-X', 'theirs'],
                            capture_output=True, text=True)
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                print(f"✗ Merge failed: {error_msg}")
                sys.exit(1)

            print(f"✓ Merged {current_branch} into {main_branch}")

        # Push to main branch
        # Use non-interactive environment to prevent GUI dialogs
        env = get_noninteractive_git_env()
        result = sp.run(['git', '-C', cwd, 'push', 'origin', main_branch], capture_output=True, text=True, env=env)
        if result.returncode == 0:
            print(f"✓ Pushed to {main_branch}")
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            if 'rejected' in error_msg and 'non-fast-forward' in error_msg:
                print(f"⚠️  Push rejected - remote has diverged. Force pushing...")
                result = sp.run(['git', '-C', cwd, 'push', '--force-with-lease', 'origin', main_branch],
                                capture_output=True, text=True, env=env)
                if result.returncode == 0:
                    print(f"✓ Force pushed to {main_branch} (remote was overwritten)")
                else:
                    print(f"✗ Force push failed: {result.stderr.strip()}")
                    sys.exit(1)
            elif 'Authentication failed' in error_msg or 'could not read Username' in error_msg or 'Permission denied' in error_msg:
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

    # Fetch first to show what we'll sync to
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

    # Get target commit info (try main, then master)
    target_ref = 'origin/main'
    target_commit = sp.run(['git', '-C', cwd, 'log', '-1', '--format=%h %s', target_ref], capture_output=True, text=True)
    if target_commit.returncode != 0:
        target_ref = 'origin/master'
        target_commit = sp.run(['git', '-C', cwd, 'log', '-1', '--format=%h %s', target_ref], capture_output=True, text=True)

    print("⚠ WARNING: This will DELETE all local changes and replace with server version!")
    if target_commit.returncode == 0:
        print(f"   Target: {target_commit.stdout.strip()}")
    skip_confirm = '--yes' in sys.argv or '-y' in sys.argv
    if not skip_confirm:
        response = input("Are you sure? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            print("✗ Cancelled")
            sys.exit(0)

    result = sp.run(['git', '-C', cwd, 'reset', '--hard', target_ref], capture_output=True, text=True)
    sp.run(['git', '-C', cwd, 'clean', '-f', '-d'], capture_output=True)
    print(f"✓ Synced with server: {target_commit.stdout.strip()}" if target_commit.returncode == 0 else "✓ Local changes removed. Synced with server.")
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
        if shutil.which('gh'):
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
            # Use the full worktree name (with project prefix) as session name
            session_name = os.path.basename(worktree_path)
            env = get_noninteractive_git_env()
            create_tmux_session(session_name, worktree_path, cmd, env=env, capture_output=False)

            if new_window:
                launch_in_new_window(session_name)
                if with_terminal:
                    launch_terminal_in_dir(worktree_path)
            elif "TMUX" in os.environ or not sys.stdout.isatty():
                # Already inside tmux or no TTY - let session run in background
                print(f"✓ Session running in background: {session_name}")
                print(f"   Reattach: aio attach")
            else:
                # Not in tmux - attach normally
                cmd = sm.attach(session_name)
                os.execvp(cmd[0], cmd)
    else:
        print(f"✗ Unknown session key: {key}")
# Removed old '+' feature (timestamped session without worktree)
# to make room for new '+' and '++' worktree commands
else:
    # If inside tmux and arg is simple agent key (c/l/g), create pane instead of session
    if 'TMUX' in os.environ and arg in sessions and len(arg) == 1:
        _, cmd = sessions[arg]
        sp.run(['tmux', 'split-window', '-h', '-c', work_dir, cmd])
        sys.exit(0)

    # Try directory-based session logic first
    session_name = get_or_create_directory_session(arg, work_dir)

    if session_name is None:
        # Not a known session key, use original behavior
        name, cmd = sessions.get(arg, (arg, None))
        # Use clean environment to prevent GUI dialogs
        env = get_noninteractive_git_env()
        create_tmux_session(name, work_dir, cmd or arg, env=env)
        session_name = name
    else:
        # Got a directory-specific session name
        # Check if it exists, create if not
        if not sm.has_session(session_name):
            # Session doesn't exist, create it
            _, cmd = sessions[arg]
            # Use clean environment to prevent GUI dialogs
            env = get_noninteractive_git_env()
            create_tmux_session(session_name, work_dir, cmd, env=env)

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
    elif "TMUX" in os.environ or not sys.stdout.isatty():
        # Already inside tmux or no TTY - let session run in background
        print(f"✓ Session running in background: {session_name}")
        print(f"   Reattach: aio attach")
    else:
        # Not in tmux - attach normally
        sp.run(sm.attach(session_name))
        print("Reattach: aio attach")
