#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1: INSTANT SHELL BOOTSTRAP (0ms)
# Add this to ~/.bashrc or ~/.zshrc for instant startup:
#
#   aio() {
#       printf "⚡ aio "  # Instant visual feedback
#       exec python3 ~/.local/bin/aio "$@"  # Hand off to Stage 2
#   }
#
# This prints "⚡ aio " BEFORE Python loads, achieving perceived 0ms startup.
# The shell function reuses the existing process (exec), no fork overhead.
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2: PURE PYTHON KERNEL (minimal imports, ~20ms)
# Only standard library imports here - no heavy deps, no I/O at module level
# ═══════════════════════════════════════════════════════════════════════════════
import os, sys, subprocess as sp, json, sqlite3, shlex, shutil, time, atexit
from datetime import datetime
from pathlib import Path

_START = time.time()
_CMD = ' '.join(sys.argv[1:3]) if len(sys.argv) > 1 else 'help'

def _save_timing():
    try:
        d = os.path.expanduser("~/.local/share/aios")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "timing.jsonl"), "a") as f:
            f.write(json.dumps({"cmd": _CMD, "ms": int((time.time() - _START) * 1000), "ts": datetime.now().isoformat()}) + "\n")
    except: pass

atexit.register(_save_timing)

# Helpers for common patterns
def _git(args, cwd=None, env=None): return sp.run(['git'] + (['-C', cwd] if cwd else []) + args, capture_output=True, text=True, env=env)
def _tmux(args): return sp.run(['tmux'] + args, capture_output=True, text=True)
def _ok(msg): print(f"✓ {msg}")
def _err(msg): print(f"✗ {msg}")
def _die(msg, code=1): _err(msg); sys.exit(code)
def _confirm(msg): return input(f"{msg} (y/n): ").strip().lower() in ['y', 'yes']

# Lazy-loaded optional dependencies
_pexpect = None
_prompt_toolkit = None

def _get_pexpect():
    """Lazy-load pexpect on first use."""
    global _pexpect
    if _pexpect is None:
        try:
            import pexpect as _p
            _pexpect = _p
        except ImportError:
            _pexpect = False
    return _pexpect if _pexpect else None

def _get_prompt_toolkit():
    """Lazy-load prompt_toolkit on first use (saves ~50ms startup)."""
    global _prompt_toolkit
    if _prompt_toolkit is None:
        try:
            from prompt_toolkit import Application
            from prompt_toolkit.layout import Layout
            from prompt_toolkit.widgets import TextArea, Frame
            from prompt_toolkit.key_binding import KeyBindings
            _prompt_toolkit = {'Application': Application, 'Layout': Layout,
                              'TextArea': TextArea, 'Frame': Frame, 'KeyBindings': KeyBindings}
        except ImportError:
            _prompt_toolkit = False
    return _prompt_toolkit if _prompt_toolkit else None

def ensure_deps(skip_check=False):
    """Check essential deps, prompt user to run 'aio install' if missing."""
    if skip_check:
        return
    missing = [c for c in ['tmux', 'claude'] if not shutil.which(c)]
    if missing: print(f"⚠ Missing: {', '.join(missing)}. Run: aio install"); sys.exit(1)

# STAGE 2: Deps check deferred to _init_stage3() - not run at import time

def input_box(prefill="", title="Ctrl+D to run, Ctrl+C to cancel"):
    # Fallback to simple input inside tmux, non-TTY, or if prompt_toolkit not installed
    pt = _get_prompt_toolkit()
    if not sys.stdin.isatty() or 'TMUX' in os.environ or not pt:
        print(f"[{title}] " if not prefill else f"[{title}]\n{prefill}\n> ", end="", flush=True)
        try:
            return input() if not prefill else prefill
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled")
            return None
    kb = pt['KeyBindings']()
    cancelled = [False]  # Use list to allow modification in closure
    @kb.add('c-d')
    def _(e): e.app.exit()
    @kb.add('c-c')
    def _(e): cancelled[0] = True; e.app.exit()
    ta = pt['TextArea'](text=prefill, multiline=True, focus_on_click=True)
    pt['Application'](layout=pt['Layout'](pt['Frame'](ta, title=title)), key_bindings=kb, full_screen=True, mouse_support=True).run()
    if cancelled[0]:
        print("Cancelled")
        return None
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
        self._ver = None  # Lazy-load version on first access
    def new_session(self, n, d, c, e=None): return sp.run(['tmux', 'new-session', '-d', '-s', n, '-c', d] + ([c] if c else []), capture_output=True, env=e)
    def send_keys(self, n, t): return sp.run(['tmux', 'send-keys', '-l', '-t', n, t])
    def attach(self, n): return ['tmux', 'attach', '-t', n]
    def has_session(self, n):
        try: return sp.run(['tmux', 'has-session', '-t', n], capture_output=True, timeout=2).returncode == 0
        except sp.TimeoutExpired: return (sp.run(['pkill', '-9', 'tmux']), False)[1] if input("⚠ tmux hung. Kill? (y/n): ").lower() == 'y' else sys.exit(1)
    def list_sessions(self): return sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True)
    def capture(self, n): return sp.run(['tmux', 'capture-pane', '-p', '-t', n], capture_output=True, text=True)
    @property
    def version(self):
        if self._ver is None:
            self._ver = sp.check_output(['tmux', '-V'], text=True).split()[1] if shutil.which('tmux') else '0'
        return self._ver

sm = TmuxManager()

def _maybe_update_tmux():
    """Auto-update tmux every 12h in background (Linux only). Called from _init_stage3()."""
    try:
        if sys.platform != 'darwin':
            _ts_dir = os.path.expanduser('~/.local/share/aios'); os.makedirs(_ts_dir, exist_ok=True)
            _ts = os.path.join(_ts_dir, '.tmux_update')
            ((not os.path.exists(_ts) or time.time()-os.path.getmtime(_ts)>43200) and os.fork()==0) and (Path(_ts).touch(),os.system(f'v=$(curl -sL api.github.com/repos/tmux/tmux/releases/latest 2>/dev/null|grep -oP \'"tag_name":"\\K[^"]+\');[ "$v" \\> "{sm.version}" ]&&cd /tmp&&rm -rf tmux-update&&git clone -q --depth 1 -b $v https://github.com/tmux/tmux tmux-update 2>/dev/null&&cd tmux-update&&sh autogen.sh>/dev/null 2>&1&&./configure --prefix=$HOME/.local>/dev/null 2>&1&&make -j$(nproc)>/dev/null 2>&1&&make install>/dev/null 2>&1'),os._exit(0))
    except: pass

# STAGE 2: Tmux auto-update deferred to _init_stage3() - not run at import time

# Auto-update: Pull latest version from git repo
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))  # realpath follows symlinks
PROMPTS_DIR = Path(SCRIPT_DIR) / 'data' / 'prompts'

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
        result = sp.run(['git', '-C', SCRIPT_DIR, 'status', '-uno'], capture_output=True, text=True)
        if 'Your branch is behind' in result.stdout: print("⚠️  Update available! Run 'aio update' to get latest version")
        else:
            try: os.remove(marker)
            except: pass

# Git helpers for common operations
def _git(path, *args, **kw): return sp.run(['git', '-C', path] + list(args), capture_output=True, text=True, **kw)
def _git_main(path):
    r = _git(path, 'symbolic-ref', 'refs/remotes/origin/HEAD')
    return r.stdout.strip().replace('refs/remotes/origin/', '') if r.returncode == 0 else ('main' if _git(path, 'rev-parse', '--verify', 'main').returncode == 0 else 'master')
def _git_push(path, branch, env, force=False):
    r = _git(path, 'push', '--force' if force else '', 'origin', branch, env=env) if force else _git(path, 'push', 'origin', branch, env=env)
    if r.returncode == 0: print(f"✓ Pushed to {branch}"); return True
    err = r.stderr.strip() or r.stdout.strip()
    if 'rejected' in err and 'non-fast-forward' in err and input("⚠️  Force push? (y/n): ").strip().lower() in ['y', 'yes']:
        _git(path, 'fetch', 'origin', env=env); return _git_push(path, branch, env, force=True)
    print(f"✗ Push failed: {err}"); return False
def _git_commit(path, msg, target=None):
    _git(path, 'add', target) if target else _git(path, 'add', '-A')
    r = _git(path, 'commit', '-m', msg)
    if r.returncode == 0: print(f"✓ Committed: {msg}"); return True
    if 'nothing to commit' in r.stdout: print("ℹ No changes"); return None
    print(f"✗ Commit failed: {r.stderr.strip() or r.stdout.strip()}"); return False

# STAGE 2: Update check deferred to _init_stage3() - not run at import time

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

            # Check if config exists
            cursor = conn.execute("SELECT COUNT(*) FROM config")
            if cursor.fetchone()[0] == 0:
                default_prompt = get_prompt('default') or ''
                conn.execute("INSERT INTO config VALUES ('claude_prompt', ?)", (default_prompt,))
                conn.execute("INSERT INTO config VALUES ('codex_prompt', ?)", (default_prompt,))
                conn.execute("INSERT INTO config VALUES ('gemini_prompt', ?)", (default_prompt,))
                conn.execute("INSERT INTO config VALUES ('worktrees_dir', ?)",
                           (os.path.expanduser("~/projects/aiosWorktrees"),))
                conn.execute("INSERT INTO config VALUES ('multi_default', 'l:3')")

            # Ensure multi_default exists for existing users
            conn.execute("INSERT OR IGNORE INTO config VALUES ('multi_default', 'l:3')")

            # Claude prefix for extended thinking (Ultrathink. increases thinking budget)
            conn.execute("INSERT OR IGNORE INTO config VALUES ('claude_prefix', 'Ultrathink. ')")

            # Check if projects exist
            cursor = conn.execute("SELECT COUNT(*) FROM projects")
            if cursor.fetchone()[0] == 0:
                # Insert default projects (aio only)
                default_projects = [
                    os.path.expanduser("~/projects/aio"),
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
                    ('lp', 'claude-p', 'claude --dangerously-skip-permissions "{CLAUDE_PROMPT}"'),
                    ('o', 'claude', 'claude --dangerously-skip-permissions')
                ]
                for key, name, cmd in default_sessions:
                    conn.execute("INSERT INTO sessions VALUES (?, ?, ?)", (key, name, cmd))

            # Add 'o' shortcut to existing databases (maps to default agent: claude)
            cursor = conn.execute("SELECT COUNT(*) FROM sessions WHERE key = 'o'")
            if cursor.fetchone()[0] == 0:
                conn.execute("INSERT INTO sessions VALUES ('o', 'claude', 'claude --dangerously-skip-permissions')")

def load_config():
    """Load configuration from database."""
    with WALManager(DB_PATH) as conn:
        cursor = conn.execute("SELECT key, value FROM config")
        config = dict(cursor.fetchall())
    return config

def get_prompt(name, show_location=False):
    """Load a prompt from data/prompts/{name}.txt file."""
    prompt_file = PROMPTS_DIR / f'{name}.txt'
    if prompt_file.exists():
        if show_location: print(f"📝 Prompt: {prompt_file}")
        return prompt_file.read_text().strip()
    return None

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

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3: HEAVY ENGINE INITIALIZATION (deferred, ~200ms)
# Database, config, and background tasks - only loaded when first needed
# ═══════════════════════════════════════════════════════════════════════════════
_stage3_initialized = False
config = {}
DEFAULT_PROMPT = None
CLAUDE_PROMPT = None
CODEX_PROMPT = None
GEMINI_PROMPT = None
CLAUDE_PREFIX = 'Ultrathink. '
WORK_DIR = None
WORKTREES_DIR = None
PROJECTS = []
APPS = []
sessions = {}

def _init_stage3(skip_deps_check=False):
    """Initialize heavy engine: database, config, background tasks. Called once on first use."""
    global _stage3_initialized, config, DEFAULT_PROMPT, CLAUDE_PROMPT, CODEX_PROMPT
    global GEMINI_PROMPT, CLAUDE_PREFIX, WORK_DIR, WORKTREES_DIR, PROJECTS, APPS, sessions

    if _stage3_initialized:
        return
    _stage3_initialized = True

    # Initialize database on first run
    init_database()

    # Load configuration from database
    config = load_config()
    DEFAULT_PROMPT = get_prompt('default')
    CLAUDE_PROMPT = config.get('claude_prompt', DEFAULT_PROMPT)
    CODEX_PROMPT = config.get('codex_prompt', DEFAULT_PROMPT)
    GEMINI_PROMPT = config.get('gemini_prompt', DEFAULT_PROMPT)
    # Claude prefix for extended thinking (e.g., "Ultrathink. " increases thinking budget)
    CLAUDE_PREFIX = config.get('claude_prefix', 'Ultrathink. ')

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

    # Background tasks (forked processes, non-blocking)
    ensure_deps(skip_check=skip_deps_check)  # Check/install deps (skip for install/deps commands)
    _maybe_update_tmux()  # Update tmux if needed
    try:
        check_for_updates_warning()  # Check git for updates
    except: pass

    # Regenerate help cache in background for true 0ms startup
    _regenerate_help_cache_bg()

def _regenerate_help_cache_bg():
    """Regenerate help+projects cache in background (forked process, non-blocking)."""
    if not hasattr(os, 'fork'):
        _regenerate_help_cache()
        return
    if os.fork() == 0:
        _regenerate_help_cache()
        # Also cache project paths for instant shell navigation
        try:
            with open(os.path.join(DATA_DIR, 'projects.txt'), 'w') as f:
                f.write('\n'.join(PROJECTS) + '\n')
        except: pass
        os._exit(0)

def _regenerate_help_cache():
    """Generate help output and save to cache file for true 0ms shell startup."""
    cache_file = os.path.join(DATA_DIR, 'help_cache.txt')
    try:
        # Build help output (same as 'aio' with no args)
        lines = [
            "aio - AI agent session manager",
            "QUICK START:",
            "  aio o               Start agent (o/l=claude c=codex g=gemini)",
            "  aio dash            Dashboard with jobs monitor",
            "  aio fix             AI finds/fixes issues",
            "  aio bug \"task\"      Fix a bug",
            "  aio feat \"task\"     Add a feature",
            "MULTI-AGENT:",
            "  aio multi c:3             Launch 3 codex in parallel worktrees",
            "  aio multi c:3 \"task\"      Launch 3 codex with custom task",
            "  aio multi c:2 l:1         Mixed: 2 codex + 1 claude",
            "  aio multi 0 c:2 \"task\"    Launch in project 0",
            "OVERNIGHT (autonomous):",
            "  aio overnight             Read aio.md, run agents, auto-review",
            "  aio on                    Shortcut for overnight",
            "  aio on c:3 l:2            Custom agent mix (max 5 default)",
            "GIT:",
            "  aio push src/ msg      Push folder with message",
            "  aio pull               Sync with server",
            "MANAGEMENT:",
            "  aio jobs            Show active jobs",
            "  aio attach          Reconnect to session",
            "  aio kill            Kill all tmux sessions",
            "  aio cleanup         Delete all worktrees",
            "  aio prompt [name]   Edit prompts (feat, fix, bug, auto, del)",
            "NOTES & BACKUP:",
            "  aio note            List notes, select to view",
            "  aio note 2          Open note #2",
            "  aio note \"text\"     Create note (first line = name)",
            "  aio gdrive          Backup status | aio gdrive login",
            "Run 'aio help' for all commands",
        ]

        # Add projects
        if PROJECTS:
            lines.append("📁 PROJECTS:")
            for i, p in enumerate(PROJECTS):
                exists = '✓' if os.path.exists(p) else '✗'
                lines.append(f"  {i}. {exists} {p}")

        # Add apps/commands
        if APPS:
            lines.append("")
            lines.append("⚡ COMMANDS:")
            for i, (n, c) in enumerate(APPS):
                display_cmd = c.replace(os.path.expanduser('~'), '~')
                if len(display_cmd) > 60:
                    display_cmd = display_cmd[:57] + "..."
                lines.append(f"  {len(PROJECTS)+i}. {n} → {display_cmd}")

        with open(cache_file, 'w') as f:
            f.write('\n'.join(lines) + '\n')
    except: pass

# ═══════════════════════════════════════════════════════════════════════════════
# GHOST SESSIONS - Pre-warm CLI tools for instant startup
# Ghosts are normal sessions (split panes, prefix typed) created early and hidden.
# On 'aio 0' we spawn ghosts predicting user wants 'aio c' soon. On 'aio c' we
# claim the ghost (rename+attach) for instant response. 5 min timeout via lazy cleanup.
# ═══════════════════════════════════════════════════════════════════════════════
_GHOST_PREFIX, _GHOST_TIMEOUT = '_aio_ghost_', 300
_GHOST_MAP = {'c': 'c', 'l': 'l', 'g': 'g', 'o': 'l', 'cp': 'c', 'lp': 'l', 'gp': 'g'}

def _ghost_spawn(dir_path, sessions_map):
    """Spawn ghost sessions (normal sessions, hidden). Reuses create_tmux_session for pane splits."""
    if not os.path.isdir(dir_path) or not shutil.which('tmux'): return
    state_file = os.path.join(DATA_DIR, 'ghost_state.json')
    # Cleanup stale ghosts (>5 min)
    try:
        with open(state_file) as f: state = json.load(f)
        if time.time() - state.get('time', 0) > _GHOST_TIMEOUT:
            for k in ['c', 'l', 'g']: sp.run(['tmux', 'kill-session', '-t', f'{_GHOST_PREFIX}{k}'], capture_output=True)
    except: pass
    # Spawn ghosts - normal sessions with prefix pre-typed (not executed)
    agent_names = {'c': 'codex', 'l': 'claude', 'g': 'gemini'}
    for key in ['c', 'l', 'g']:
        ghost = f'{_GHOST_PREFIX}{key}'
        if sm.has_session(ghost):
            r = sp.run(['tmux', 'display-message', '-p', '-t', ghost, '#{pane_current_path}'], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip() == dir_path: continue  # Already correct
            sp.run(['tmux', 'kill-session', '-t', ghost], capture_output=True)
        _, cmd = sessions_map.get(key, (None, None))
        if cmd:
            create_tmux_session(ghost, dir_path, cmd)  # Normal session with splits
            prefix = get_agent_prefix(agent_names[key], dir_path)
            if prefix: sp.Popen([sys.executable, __file__, 'send', ghost, prefix, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    try:
        with open(state_file, 'w') as f: json.dump({'dir': dir_path, 'time': time.time()}, f)
    except: pass

def _ghost_claim(agent_key, target_dir):
    """Claim ghost for instant startup. Returns ghost name or None (fallback to fresh spawn)."""
    ghost = f'{_GHOST_PREFIX}{_GHOST_MAP.get(agent_key, agent_key)}'
    if not sm.has_session(ghost): return None
    r = sp.run(['tmux', 'display-message', '-p', '-t', ghost, '#{pane_current_path}'], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != target_dir:
        sp.run(['tmux', 'kill-session', '-t', ghost], capture_output=True); return None
    return ghost

# ═══════════════════════════════════════════════════════════════════════════════
# RCLONE GOOGLE DRIVE SYNC - minimal integration for data backup
# ═══════════════════════════════════════════════════════════════════════════════
RCLONE_REMOTE = 'aio-gdrive'
RCLONE_BACKUP_PATH = 'aio-backup'

def _rclone_configured():
    """Check if rclone gdrive remote is configured."""
    r = sp.run(['rclone', 'listremotes'], capture_output=True, text=True) if shutil.which('rclone') else None
    return r and f'{RCLONE_REMOTE}:' in r.stdout

def _rclone_account():
    """Get Google account email from Drive API. Returns 'Name <email>' or None."""
    try:
        r = sp.run(['rclone', 'config', 'dump'], capture_output=True, text=True)
        token = json.loads(json.loads(r.stdout).get(RCLONE_REMOTE, {}).get('token', '{}')).get('access_token')
        if not token: return None
        import urllib.request
        req = urllib.request.Request('https://www.googleapis.com/drive/v3/about?fields=user', headers={'Authorization': f'Bearer {token}'})
        user = json.loads(urllib.request.urlopen(req, timeout=5).read()).get('user', {})
        return f"{user.get('displayName', '')} <{user.get('emailAddress', 'unknown')}>"
    except: return None

_RCLONE_ERR_FILE = Path(DATA_DIR) / '.rclone_err'

def _rclone_sync_data(wait=False):
    """Sync data folder to Google Drive. Returns (started, success) if wait, else (started, None)."""
    if not _rclone_configured(): return False, None
    def _sync():
        r = sp.run(['rclone', 'sync', str(Path(SCRIPT_DIR) / 'data'), f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}', '-q'], capture_output=True, text=True)
        _RCLONE_ERR_FILE.write_text(r.stderr) if r.returncode != 0 else _RCLONE_ERR_FILE.unlink(missing_ok=True)
        return r.returncode == 0
    if wait: return True, _sync()
    __import__('threading').Thread(target=_sync, daemon=True).start()
    return True, None

def _rclone_pull_notes():
    """Pull newer notes from Google Drive (non-destructive, only adds/updates)."""
    if not _rclone_configured(): return False
    sp.run(['rclone', 'copy', f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}/notebook', str(Path(SCRIPT_DIR) / 'data' / 'notebook'), '-u', '-q'], capture_output=True)
    return True

_AGENT_DIRS = {'claude': Path.home()/'.claude', 'codex': Path.home()/'.codex', 'gemini': Path.home()/'.gemini'}

def _rclone_sync_agents(wait=False):
    """Backup claude/codex/gemini configs to Google Drive."""
    if not _rclone_configured(): return False, None
    def _sync(): return all(sp.run(['rclone', 'copy', str(p), f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}/agents/{n}', '-u', '-q'], capture_output=True).returncode == 0 for n, p in _AGENT_DIRS.items() if p.exists())
    if wait: return True, _sync()
    __import__('threading').Thread(target=_sync, daemon=True).start(); return True, None

_TMUX_CONF = os.path.expanduser('~/.tmux.conf')
_AIO_MARKER = '# aio-managed-config'

def _get_clipboard_cmd():
    """Detect platform-appropriate clipboard command for tmux copy."""
    import sys
    if os.environ.get('TERMUX_VERSION'):
        return 'termux-clipboard-set'
    elif sys.platform == 'darwin':
        return 'pbcopy'
    elif shutil.which('xclip'):
        return 'xclip -selection clipboard -i'
    elif shutil.which('xsel'):
        return 'xsel --clipboard --input'
    return None

def _write_tmux_conf():
    """Write tmux config to ~/.tmux.conf for persistence across restarts.

    TERMUX NOTE: Config is per-user (~/.tmux.conf). Termux has no system-wide
    config, so each user must run aio once to set up their tmux environment.
    The config persists across tmux/terminal restarts automatically.
    """
    line0 = '#[align=left][#S]#[align=centre]#{W:#[range=window|#{window_index}]#I:#W#{?window_active,*,}#[norange] }'
    sh_full = '#[range=user|sess]Ctrl+N:Win#[norange] #[range=user|new]Ctrl+T:New#[norange] #[range=user|close]Ctrl+W:Close#[norange] #[range=user|edit]Ctrl+E:Edit#[norange] #[range=user|kill]Ctrl+X:Kill#[norange] #[range=user|detach]Ctrl+Q:Quit#[norange]'
    sh_min = '#[range=user|sess]Sess#[norange] #[range=user|new]New#[norange] #[range=user|close]Close#[norange] #[range=user|edit]Edit#[norange] #[range=user|kill]Kill#[norange] #[range=user|detach]Quit#[norange]'
    line1 = '#{?#{e|<:#{client_width},70},' + sh_min + ',' + sh_full + '}'
    line2 = '#[align=left]#[range=user|esc]⎋ Esc#[norange]#[align=centre]#[range=user|kbd]⌨ Keyboard#[norange]'
    clip_cmd = _get_clipboard_cmd()
    conf = f'''{_AIO_MARKER}
set -g mouse on
set -g focus-events on
set -g set-titles on
set -g set-titles-string "#S:#W"
set -s set-clipboard off
set -g visual-bell off
set -g bell-action any
set -g status-position bottom
set -g status 3
set -g status-right ""
set -g status-format[0] "{line0}"
set -g status-format[1] "#[align=centre]{line1}"
set -g status-format[2] "{line2}"
bind-key -n C-n new-window
bind-key -n C-t split-window
bind-key -n C-w kill-pane
bind-key -n C-q detach
bind-key -n C-x confirm-before -p "Kill session? (y/n)" kill-session
bind-key -n C-e split-window "nvim ."
bind-key -T root MouseDown1Status if -F '#{{==:#{{mouse_status_range}},window}}' {{ select-window }} {{ run-shell 'r="#{{mouse_status_range}}"; case "$r" in sess) tmux new-window;; new) tmux split-window;; close) tmux kill-pane;; edit) tmux split-window nvim;; kill) tmux confirm-before -p "Kill?" kill-session;; detach) tmux detach;; esc) tmux send-keys Escape;; kbd) tmux set -g mouse off; tmux display-message "Tap terminal - mouse restores in 3s"; (sleep 3; tmux set -g mouse on) &;; esac' }}
'''
    # Add mouse copy-on-selection (copies to clipboard when mouse selection ends)
    if clip_cmd:
        conf += f'bind-key -T copy-mode MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "{clip_cmd}"\n'
        conf += f'bind-key -T copy-mode-vi MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "{clip_cmd}"\n'
    if sm.version >= '3.6':
        conf += 'set -g pane-scrollbars on\nset -g pane-scrollbars-position right\n'

    # Always write config to ensure latest version is applied
    with open(_TMUX_CONF, 'w') as f:
        f.write(conf)
    return True

def ensure_tmux_options():
    """Configure tmux: 3-line status bar, mouse, scrollbars, keyboard shortcuts.

    Status bar layout:
      Line 0: [session] window list
      Line 1: Ctrl+T:New  Ctrl+W:Close  Ctrl+E:Edit  Ctrl+X:Kill  Ctrl+Q:Detach
      Line 2: ⌨ Keyboard (tapping triggers virtual keyboard on Termux)

    Always writes and sources config to ensure changes are applied immediately.
    """
    # Always write config
    _write_tmux_conf()

    # Apply to running tmux if available
    if sp.run(['tmux', 'info'], stdout=sp.DEVNULL, stderr=sp.DEVNULL).returncode != 0: return

    # Source the config file to apply settings
    result = sp.run(['tmux', 'source-file', _TMUX_CONF], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠ tmux config error: {result.stderr.strip()}")
        return
    sp.run(['tmux', 'refresh-client', '-S'], capture_output=True)

# Defer tmux options until first session is created (saves ~10ms on startup)
# ensure_tmux_options() is called in create_tmux_session() instead

# Termux: Check for termux-api (needed for keyboard button) - only on Termux
_TERMUX_DIALOG = '/data/data/com.termux/files/usr/bin/termux-dialog'

def create_tmux_session(session_name, work_dir, cmd, env=None, capture_output=True):
    """Create a tmux session with enhanced options. Agent sessions get agent+bash panes."""
    result = sm.new_session(session_name, work_dir, cmd or '', env)
    ensure_tmux_options()  # After session creation so tmux server is running
    # Auto-add bash pane for agent sessions (agent top, bash bottom)
    if cmd and any(a in cmd for a in ['codex', 'claude', 'gemini']):
        sp.run(['tmux', 'split-window', '-v', '-t', session_name, '-c', work_dir, 'bash -c "ls;exec bash"'], capture_output=True)
        sp.run(['tmux', 'select-pane', '-t', session_name, '-U'], capture_output=True)
        # Activity monitor: green on output, red after 5s silence, exit on EOF
        sn = shlex.quote(session_name)
        monitor_script = f"bash -c 's={sn}; while :; do read -t5 && c=🟢 || (($?>128)) && c=🔴 || exit; tmux set -t $s set-titles-string \"$c #S:#W\"; done'"
        sp.run(['tmux', 'pipe-pane', '-t', session_name, '-o', monitor_script], capture_output=True)
    return result

def detect_terminal():
    """Detect available terminal emulator"""
    for term in ['ptyxis', 'gnome-terminal', 'alacritty']:
        if shutil.which(term):
            return term
    return None

# Font size controller - data-driven approach
import re as _re
_FONT_CFG = {'termux': {'env': 'TERMUX_VERSION', 'help': '📱 Pinch zoom | Ctrl+Alt++/-'},
    'kitty': {'env': 'KITTY_WINDOW_ID', 'help': 'Ctrl+Shift+= / Ctrl+Shift+-'},
    'alacritty': {'env': 'ALACRITTY_WINDOW_ID', 'help': 'Ctrl+= / Ctrl+-'},
    'gnome': {'env': ['GNOME_TERMINAL_SCREEN', 'VTE_VERSION'], 'req': 'gsettings', 'help': 'Ctrl+Shift++ / Ctrl+-'}}
def _font_detect():
    for n, c in _FONT_CFG.items():
        envs = c['env'] if isinstance(c['env'], list) else [c['env']]
        if any(os.environ.get(e) for e in envs) and (not c.get('req') or shutil.which(c['req'])): return n, c
    return None, None
def _font_get(n, c):
    if n == 'kitty':
        r = sp.run(['kitty', '@', 'get-colors'], capture_output=True, text=True)
        return next((int(float(l.split()[-1])) for l in r.stdout.split('\n') if 'font_size' in l), None) if r.returncode == 0 else None
    if n == 'gnome':
        try:
            p = sp.run(['gsettings', 'get', 'org.gnome.Terminal.ProfilesList', 'default'], capture_output=True, text=True).stdout.strip().strip("'")
            return int(sp.run(['gsettings', 'get', f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{p}/', 'font'], capture_output=True, text=True).stdout.strip().strip("'").split()[-1])
        except: return None
    if n == 'alacritty':
        for p in [os.path.expanduser(x) for x in ['~/.config/alacritty/alacritty.toml', '~/.config/alacritty/alacritty.yml', '~/.alacritty.toml']]:
            if os.path.exists(p) and (m := _re.search(r'size\s*[=:]\s*(\d+(?:\.\d+)?)', Path(p).read_text())): return int(float(m.group(1)))
    return None
def _font_set(n, c, sz):
    if n == 'termux': print(f"⚠️ Termux: {c['help']}"); return False
    if n == 'kitty' and sp.run(['kitty', '@', 'set-font-size', str(sz)], capture_output=True).returncode == 0: print(f"✓ Font size set to {sz}"); return True
    if n == 'gnome':
        try:
            p = sp.run(['gsettings', 'get', 'org.gnome.Terminal.ProfilesList', 'default'], capture_output=True, text=True).stdout.strip().strip("'")
            f = sp.run(['gsettings', 'get', f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{p}/', 'font'], capture_output=True, text=True).stdout.strip().strip("'")
            sp.run(['gsettings', 'set', f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{p}/', 'font', f"{' '.join(f.split()[:-1])} {sz}"], capture_output=True); print(f"✓ Font size set to {sz}"); return True
        except: return False
    if n == 'alacritty':
        cp = next((os.path.expanduser(x) for x in ['~/.config/alacritty/alacritty.toml', '~/.config/alacritty/alacritty.yml'] if os.path.exists(os.path.expanduser(x))), os.path.expanduser('~/.config/alacritty/alacritty.toml'))
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        if not os.path.exists(cp): Path(cp).write_text(f'[font]\nsize = {sz}\n'); print(f"✓ Created {cp}"); return True
        t = Path(cp).read_text(); Path(cp).write_text(_re.sub(r'(size\s*[=:]\s*)\d+(?:\.\d+)?', f'\\g<1>{sz}', t) if _re.search(r'size\s*[=:]\s*\d+', t) else t + f'\n[font]\nsize = {sz}\n'); print(f"✓ Font size set to {sz}"); return True
    return False
def handle_font_command(args):
    n, c = _font_detect()
    if not n: print("✗ Unknown terminal"); return
    print(f"Terminal: {n}")
    if not args: sz = _font_get(n, c); print(f"Current font size: {sz}" if sz else c['help']); return
    a = args[0]; d = int(args[1]) if len(args) > 1 else 2
    if a in ['+', 'up', 'bigger'] and (sz := _font_get(n, c)): _font_set(n, c, sz + d)
    elif a in ['-', 'down', 'smaller'] and (sz := _font_get(n, c)): _font_set(n, c, sz - d)
    elif a.isdigit(): _font_set(n, c, int(a))
    elif a == 'help': print(c['help'])
    else: print("Usage: aio font [+|-|SIZE|help]")

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

    tmux_sessions = result.stdout.strip().split('\n')

    # Check each session's current path
    for session in tmux_sessions:
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
    pexpect = _get_pexpect()
    if not pexpect:
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

def is_claude_session(session_name):
    """Check if a session is a Claude session (l, lp, o keys map to claude)."""
    return 'claude' in session_name.lower()

def is_worktree_merged(path):
    """Check if worktree has no diff from origin/main and no untracked files."""
    sp.run(['git', '-C', path, 'fetch', 'origin'], capture_output=True)
    diff = sp.run(['git', '-C', path, 'diff', 'origin/main'], capture_output=True, text=True)
    if diff.returncode != 0: return False  # No origin/main, keep worktree
    untracked = sp.run(['git', '-C', path, 'ls-files', '--others', '--exclude-standard'], capture_output=True, text=True).stdout.strip()
    return not diff.stdout and not untracked

def get_agent_prefix(agent, work_dir=None):
    """Get prefix to pre-type for agent (Ultrathink for claude + AGENTS.md for all)."""
    prefix = config.get('claude_prefix', 'Ultrathink. ') if 'claude' in agent else ''
    agents = Path(work_dir or os.getcwd()) / 'AGENTS.md'
    return prefix + (agents.read_text().strip() + ' ' if agents.exists() else '')

def enhance_prompt(prompt, agent='', work_dir=None):
    """Add agent prefix and AGENTS.md to prompts."""
    prefix = get_agent_prefix(agent, work_dir)
    return (prefix if prefix and not prompt.startswith(prefix.strip()) else '') + prompt

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

    # Add Ultrathink. prefix for Claude sessions (increases thinking budget)
    prompt = enhance_prompt(prompt, session_name)

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
        tmux_sessions = [s for s in result.stdout.strip().split('\n') if s]

        # Get directory for each session
        for session in tmux_sessions:
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

    for job_path in list(jobs_by_path.keys()):
        # Skip deleted directories
        if not os.path.exists(job_path):
            for s in jobs_by_path[job_path]: sp.run(['tmux', 'kill-session', '-t', s], capture_output=True)
            continue
        # Auto-cleanup merged worktrees (no diff from main, no untracked, no active session)
        if job_path.startswith(WORKTREES_DIR) and not jobs_by_path[job_path] and is_worktree_merged(job_path):
            sp.run(['git', 'worktree', 'remove', '--force', job_path], capture_output=True)
            print(f"🧹 Auto-cleaned merged worktree: {os.path.basename(job_path)}")
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
        # Get diff stats (for worktree containers, check parent project)
        import re
        diff_path = job_path
        if is_worktree:
            parent = os.path.join(os.path.expanduser('~/projects'), job_name)
            if os.path.isdir(parent): diff_path = parent
        diff_stat = sp.run(['git', '-C', diff_path, 'diff', 'origin/main', '--shortstat'], capture_output=True, text=True)
        if diff_stat.returncode == 0 and not diff_stat.stdout.strip() and is_worktree and not sessions_in_job:
            shutil.rmtree(job_path, ignore_errors=True)
            print(f"🧹 Removed synced worktree: {job_name}")
            continue
        diff_info = ""
        if diff_stat.returncode == 0:
            if diff_stat.stdout.strip():
                m = re.search(r'(\d+) insertion.*?(\d+) deletion|(\d+) insertion|(\d+) deletion', diff_stat.stdout)
                if m: diff_info = f" ({'+' + (m.group(1) or m.group(3) or '0')}/{'-' + (m.group(2) or m.group(4) or '0')} vs origin)"
            else:
                diff_info = " (=origin)"

        print(f"  {status_display}  {job_name}{type_indicator}{time_indicator}{diff_info}")
        print(f"           aio {job_path.replace(os.path.expanduser('~'), '~')}")
        for s in sessions_in_job: print(f"           tmux attach -t {s}")
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

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT - STAGE 2 CONTINUES: Fast arg parsing, defer heavy init
# ═══════════════════════════════════════════════════════════════════════════════
arg = sys.argv[1] if len(sys.argv) > 1 else None

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2 PERFORMANCE GUARD: Must complete in <50ms or system errors
# This enforces that aio stays instant. If Stage 2 exceeds 50ms, something is
# wrong (heavy import at module level, blocking I/O, etc.) and must be fixed.
# ═══════════════════════════════════════════════════════════════════════════════
_STAGE2_MAX_MS = 50
_stage2_ms = int((time.time() - _START) * 1000)
if _stage2_ms > _STAGE2_MAX_MS:
    print(f"⚠️  PERFORMANCE ERROR: Stage 2 took {_stage2_ms}ms (max {_STAGE2_MAX_MS}ms)")
    print(f"   aio must start instantly. Something is blocking at module level.")
    print(f"   Check for: heavy imports, I/O operations, network calls at import time.")
    sys.exit(1)

# Initialize Stage 3 (heavy engine) - this is where the ~200ms cost goes
# Called once, caches result for subsequent calls
# Skip deps check for install/deps commands so they can bootstrap without blocking
_init_stage3(skip_deps_check=(arg in ('install', 'deps')))

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

# Commands that take numeric args (don't execute commands for these)
_cmd_keywords = {'add', 'remove', 'rm', 'cmd', 'command', 'commands', 'app', 'apps', 'prompt', 'multi', 'review', 'w'}

if work_dir_arg and work_dir_arg.isdigit() and arg not in _cmd_keywords:
    idx = int(work_dir_arg)
    if 0 <= idx < len(PROJECTS):
        work_dir = PROJECTS[idx]
    elif 0 <= idx - len(PROJECTS) < len(APPS):
        # Execute command using user's shell (not /bin/sh which lacks python etc.)
        app_name, app_command = APPS[idx - len(PROJECTS)]
        print(f"▶️  Running: {app_name}")
        print(f"   Command: {app_command}")
        shell = os.environ.get('SHELL', '/bin/bash')
        os.execvp(shell, [shell, '-c', app_command])
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
    display_cmd = app_cmd.replace(os.path.expanduser('~'), '~')
    return display_cmd[:max_length-3] + "..." if len(display_cmd) > max_length else display_cmd

def list_all_items(show_help=True):
    """Display projects and apps with unified numbering. Returns (projects, apps)."""
    projects, apps = load_projects(), load_apps()
    if projects:
        print("📁 PROJECTS:")
        for i, p in enumerate(projects):
            print(f"  {i}. {'✓' if os.path.exists(p) else '✗'} {p}")
    if apps:
        if projects: print()
        print("⚡ COMMANDS:")
        for i, (n, c) in enumerate(apps):
            print(f"  {len(projects)+i}. {n} → {format_app_command(c)}")
    if show_help and (projects or apps):
        print(f"\n💡 aio add [path|name cmd]  aio remove <#|name>")
    return projects, apps

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
    """Create git worktree. Returns (path, used_local) or (auth_ok, fix_cmd) if check_only."""
    check_only or os.makedirs(WORKTREES_DIR, exist_ok=True)
    proj_name = os.path.basename(project_path)
    branch = _git(project_path, 'branch', '--show-current').stdout.strip() or 'main'
    print(f"{'   Checking auth...' if check_only else '⬇️  Fetching...'}", end='', flush=True)
    env = get_noninteractive_git_env()
    r = _git(project_path, 'fetch', 'origin', env=env)
    if r.returncode == 0:
        print(" ✓");
        if check_only: return (True, None)
        fetch_ok = True
    else:
        err = r.stderr.strip()
        if any(x in err for x in ['Authentication', 'Username', 'Permission']):
            print(" ❌")
            url = _git(project_path, 'remote', 'get-url', 'origin').stdout.strip()
            fix = f"cd {project_path} && git remote set-url origin {url.replace('https://github.com/', 'git@github.com:')}" if 'https://github.com/' in url else None
            if check_only: return (False, fix)
            print(f"⚠️ Using LOCAL (fix: switch to SSH)"); fetch_ok = False
        else:
            print(f" ⚠️");
            if check_only: return (True, None)
            fetch_ok = True
    if check_only: return (True, None)
    wt_name, wt_path = f"{proj_name}-{session_name}", os.path.join(WORKTREES_DIR, f"{proj_name}-{session_name}")
    src = f"origin/{branch}" if fetch_ok else branch
    r = _git(project_path, 'worktree', 'add', '-b', f"wt-{wt_name}", wt_path, src)
    print("✓" if r.returncode == 0 else f"✗ {r.stderr.strip()}")
    return (wt_path if r.returncode == 0 else None, not fetch_ok)

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
        _ghost_spawn(project_path, sessions)  # Pre-warm agents - user likely wants 'aio c' soon
        os.chdir(project_path)
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    elif 0 <= idx - len(PROJECTS) < len(APPS):
        # Execute command using user's shell
        app_name, app_command = APPS[idx - len(PROJECTS)]
        print(f"▶️  Running: {app_name}")
        print(f"   Command: {format_app_command(app_command)}")
        shell = os.environ.get('SHELL', '/bin/bash')
        os.execvp(shell, [shell, '-c', app_command])
        sys.exit(0)
    else:
        print(f"✗ Invalid index: {idx} (valid: 0-{len(PROJECTS) + len(APPS) - 1})")
        sys.exit(1)

# Handle worktree commands (but not 'watch' or existing files like 'webgpu-walk.html')
if arg and arg.startswith('w') and arg != 'watch' and not os.path.isfile(arg):
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

# Internal: ghost spawn from shell function (background, minimal output)
if arg == '_ghost':
    if len(sys.argv) > 2:
        _init_stage3()
        _ghost_spawn(sys.argv[2], sessions)
    sys.exit(0)

if not arg:
    print(f"""aio - AI agent session manager
QUICK START:
  aio c               Start agent (c=codex l/o=claude g=gemini)
  aio dash            Dashboard with jobs monitor
  aio fix             AI finds/fixes issues
  aio bug "task"      Fix a bug
  aio feat "task"     Add a feature
MULTI-AGENT:
  aio multi c:3             Launch 3 codex in parallel worktrees
  aio multi c:3 "task"      Launch 3 codex with custom task
  aio multi c:2 l:1         Mixed: 2 codex + 1 claude
  aio multi 0 c:2 "task"    Launch in project 0
OVERNIGHT (autonomous):
  aio overnight             Read aio.md, run agents, auto-review
  aio on                    Shortcut for overnight
  aio on c:3 l:2            Custom agent mix (max 5 default)
GIT:
  aio push src/ msg      Push folder with message
  aio pull               Sync with server
MANAGEMENT:
  aio jobs            Show active jobs
  aio attach          Reconnect to session
  aio kill            Kill all tmux sessions
  aio cleanup         Delete all worktrees
  aio prompt [name]   Edit prompts (feat, fix, bug, auto, del)
NOTES & BACKUP:
  aio note            List notes, select to view
  aio note 2          Open note #2
  aio note "text"     Create note (first line = name)
  aio gdrive          Backup status | aio gdrive login
Run 'aio help' for all commands""")
    list_all_items(show_help=False)
elif arg == 'help' or arg == '--help' or arg == '-h':
    print(f"""aio - AI agent session manager
SESSIONS: c=codex l/o=claude g=gemini h=htop t=top
  aio <key> [#|dir]      Start session (# = project index)
  aio <key>-- [#]        New worktree  |  aio +<key>  New timestamped
  aio cp/lp/gp           Insert prompt (edit first)
  aio cpp/lpp/gpp        Auto-run prompt
  aio <key> "prompt"     Send custom prompt  |  -w new window  -t +terminal

WORKFLOWS: aio fix|bug|feat|auto|del [agent] ["task"]
  fix=autonomous  bug=debug  feat=add  auto=improve  del=cleanup

OVERNIGHT: aio on [#] [c:N l:N]  Read aio.md, agents work, auto-review
IDEA: aio idea [#|path] [l:N]   Agents use project as customer → ISSUES.md

WORKTREES: aio w  list | w<#>  open | w<#>-  delete | w<#>--  push+delete

ADD/REMOVE: aio add [path|name "cmd"]  aio remove <#|name>
  aio add           Add cwd as project  |  aio add mycmd "echo hi"  Add command
  aio remove 0      Remove by number    |  aio remove mycmd         By name

MONITOR: jobs [-r] | review | cleanup | ls | attach | kill
  multi <#> c:N l:N "task"  Parallel agents
  send <sess> "text"  |  watch <sess> [sec]

GIT: push [file] [msg] | pull [-y] | revert [N] | setup <url>

CONFIG: install | deps | update | font [+|-|N] | config [key] [val]
  claude_prefix="Ultrathink. "  (auto-prefixes Claude prompts)

NOTES: note [#|content] - markdown notes, first line becomes name
  note          List & select  |  note 2        Open note #2
  note "hello"  Create note    |  auto-syncs to Google Drive

BACKUP: gdrive [login] - auto-syncs data/ to Google Drive on note save

FLAGS: -w new-window  -t with-terminal  -y skip-confirm
DB: ~/.local/share/aios/aio.db  Worktrees: {WORKTREES_DIR}""")
    list_all_items(show_help=False)
elif arg == 'dir' or (arg and os.path.isdir(os.path.expanduser(arg))) or (arg and arg.startswith('/projects/') and os.path.isdir(os.path.expanduser('~' + arg))):
    d = os.path.expanduser('~' + arg) if arg.startswith('/projects/') else (os.path.expanduser(arg) if arg != 'dir' else os.getcwd())
    print(f"📂 {d}", flush=True); sp.run(['ls', d])
elif arg == 'diff':
    import re; sp.run(['git', 'fetch', 'origin'], capture_output=True)
    cwd = os.getcwd()
    b = sp.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True).stdout.strip()
    target = 'origin/main' if b.startswith('wt-') else f'origin/{b}'
    diff = sp.run(['git', 'diff', target], capture_output=True, text=True).stdout
    untracked = sp.run(['git', 'ls-files', '--others', '--exclude-standard'], capture_output=True, text=True).stdout.strip()
    print(f"📂 {cwd}")
    print(f"🌿 {b} → {target}")
    if not diff and not untracked: print("No changes"); sys.exit(0)
    G, R, X, f, LINE_RE = '\033[48;2;26;84;42m', '\033[48;2;117;34;27m', '\033[0m', '', re.compile(r'\+(\d+)')
    if diff:
        print(sp.run(['git', 'diff', target, '--shortstat'], capture_output=True, text=True).stdout.strip() + "\n")
        for L in diff.split('\n'):
            if L.startswith('diff --git'): f = L.split(' b/')[-1]
            elif L.startswith('@@'): m = LINE_RE.search(L); print(f"\n{f} line {m.group(1)}:" if m else "")
            elif L.startswith('+') and not L.startswith('+++'): print(f"  {G}+ {L[1:]}{X}")
            elif L.startswith('-') and not L.startswith('---'): print(f"  {R}- {L[1:]}{X}")
    if untracked: print(f"\nUntracked files:\n" + '\n'.join(f"  {G}+ {u}{X}" for u in untracked.split('\n')))
elif arg == 'update':
    # Explicitly update aio from git repository
    manual_update()
elif arg == 'font':
    # Font size control
    handle_font_command(sys.argv[2:])
elif arg in ('fix', 'bug', 'feat', 'auto', 'del'):
    # Prompt-based sessions: aio fix, aio bug "task", aio feat "task", aio auto, aio del
    args = sys.argv[2:]
    agent = 'l'  # Default to claude
    if args and args[0] in ('c', 'l', 'g'):
        agent, args = args[0], args[1:]
    prompt_template = get_prompt(arg, show_location=True) or '{task}'
    if arg in ('fix', 'auto', 'del'):
        prompt, task = prompt_template, 'autonomous'
    else:
        task = ' '.join(args) if args else input(f"{arg}: ")
        prompt = prompt_template.format(task=task)
    agent_name, cmd = sessions[agent]
    session_name = f"{arg}-{agent}-{datetime.now().strftime('%H%M%S')}"
    print(f"📝 {arg.upper()} [{agent_name}]: {task[:50]}{'...' if len(task) > 50 else ''}")
    prompt = enhance_prompt(prompt, agent_name)
    create_tmux_session(session_name, os.getcwd(), f"{cmd} {shlex.quote(prompt)}")
    launch_in_new_window(session_name) if 'TMUX' in os.environ else os.execvp(sm.attach(session_name)[0], sm.attach(session_name))
elif arg == 'install':
    bin_dir, script_path = os.path.expanduser("~/.local/bin"), os.path.realpath(__file__)
    os.makedirs(bin_dir, exist_ok=True)
    aio_link = os.path.join(bin_dir, "aio")
    if os.path.islink(aio_link): os.remove(aio_link)
    elif os.path.exists(aio_link): _die(f"✗ {aio_link} exists but is not a symlink")
    os.symlink(script_path, aio_link); print(f"✓ Symlink: {aio_link}")
    shell = os.environ.get('SHELL', '/bin/bash')
    rc = os.path.expanduser('~/.config/fish/config.fish' if 'fish' in shell else ('~/.zshrc' if 'zsh' in shell else '~/.bashrc'))
    func = '''# aio instant startup (Stage 1: true 0ms) - Added by aio install
function aio
    cat ~/.local/share/aios/help_cache.txt 2>/dev/null; or command python3 ~/.local/bin/aio $argv
end''' if 'fish' in shell else '''# aio instant startup (Stage 1: true 0ms) - Added by aio install
aio() {
    local cache=~/.local/share/aios/help_cache.txt projects=~/.local/share/aios/projects.txt
    if [[ "$1" =~ ^[0-9]+$ ]]; then local dir=$(sed -n "$((${1}+1))p" "$projects" 2>/dev/null); [[ -d "$dir" ]] && { echo "📂 $dir"; cd "$dir"; return; }; fi
    local d="${1/#~/$HOME}"; [[ "$1" == /projects/* ]] && d="$HOME$1"; [[ -d "$d" ]] && { echo "📂 $d"; cd "$d"; ls; return; }
    [[ -z "$1" || "$1" == "help" || "$1" == "-h" ]] && { cat "$cache" 2>/dev/null || command python3 ~/.local/bin/aio "$@"; return; }
    command python3 ~/.local/bin/aio "$@"
}'''
    if 'aio instant startup' not in (Path(rc).read_text() if os.path.exists(rc) else ''):
        try:
            if input(f"Add instant startup to {rc}? [Y/n]: ").strip().lower() != 'n':
                Path(rc).open('a').write(func + '\n'); print(f"✓ Added to {rc}")
        except: pass
    if 'bash' in shell:
        bp = os.path.expanduser('~/.bash_profile')
        if not os.path.exists(bp) or 'bashrc' not in Path(bp).read_text(): Path(bp).open('a').write('source ~/.bashrc\n')
    if bin_dir not in os.environ.get('PATH', '') and '.local/bin' not in (Path(rc).read_text() if os.path.exists(rc) else ''):
        try:
            if input(f"Add ~/.local/bin to PATH in {rc}? [Y/n]: ").strip().lower() != 'n':
                Path(rc).open('a').write('\nexport PATH="$HOME/.local/bin:$PATH"\n'); print(f"✓ Added PATH")
        except: pass
    def _ok(p):
        try: return bool(shutil.which(p)) if p in 'tmux npm codex claude gemini'.split() else (__import__(p), True)[1]
        except: return False
    _a, _n = {'pexpect': 'python3-pexpect', 'prompt_toolkit': 'python3-prompt-toolkit', 'tmux': 'tmux'}, {'codex': '@openai/codex', 'claude': '@anthropic-ai/claude-code', 'gemini': '@google/gemini-cli'}
    ok, am, nm = [p for p in list(_a)+list(_n)+['npm'] if _ok(p)], ' '.join(_a[p] for p in _a if not _ok(p)), ' '.join(_n[p] for p in _n if not _ok(p))
    ok and print(f"✓ Have: {', '.join(ok)}")
    am and shutil.which('apt-get') and (print(f"\n📦 Run: sudo apt install {am}\n"), input("Press Enter when done..."))
    nm and print(f"\n📦 Run: {'npm' if shutil.which('npm') else 'Install Node.js, then: npm'} install -g {nm}")
elif arg == 'deps':
    import platform, urllib.request, tarfile, lzma
    _w, bin_dir = shutil.which, os.path.expanduser('~/.local/bin'); os.makedirs(bin_dir, exist_ok=True)
    def _i(p, a=None):  # Install pkg: try import -> apt -> pip -> pip+break -> pkg
        try: __import__(p); print(f"✓ {p}"); return True
        except: pass
        if a and _w('apt-get') and sp.run(['sudo','apt-get','install','-y',a], capture_output=True).returncode == 0: print(f"✓ {p}"); return True
        for brk in [[], ['--break-system-packages']]:
            if sp.run([sys.executable,'-m','pip','install','--user']+brk+[p], capture_output=True).returncode == 0: print(f"✓ {p}"); return True
        if _w('pkg') and sp.run(['pkg','install','-y',f'python-{p}'], capture_output=True).returncode == 0: print(f"✓ {p}"); return True
        print(f"✗ {p}"); return False
    print("📦 Installing deps...\n")
    _i('pexpect', 'python3-pexpect'); _i('prompt_toolkit', 'python3-prompt-toolkit')
    if not _w('tmux'):
        cmds = [['brew', 'install', 'tmux']] if sys.platform == 'darwin' else ([['sudo', 'apt-get', 'install', '-y', 'tmux']] if _w('apt-get') else [['pkg', 'install', '-y', 'tmux']])
        any(sp.run(c, capture_output=True).returncode == 0 for c in cmds) and print("✓ tmux") or print("✗ tmux")
    else: print("✓ tmux")
    node_dir, node_bin = os.path.expanduser('~/.local/node'), os.path.expanduser('~/.local/node/bin')
    npm_path = os.path.join(node_bin, 'npm')
    if not _w('npm') and not os.path.exists(npm_path):
        arch, plat = 'x64' if platform.machine() in ('x86_64', 'AMD64') else 'arm64', 'darwin' if sys.platform == 'darwin' else 'linux'
        try:
            urllib.request.urlretrieve(f'https://nodejs.org/dist/v22.11.0/node-v22.11.0-{plat}-{arch}.tar.xz', '/tmp/node.tar.xz')
            with lzma.open('/tmp/node.tar.xz') as xz: tarfile.open(fileobj=xz).extractall(os.path.expanduser('~/.local'), filter='data')
            os.rename(os.path.expanduser(f'~/.local/node-v22.11.0-{plat}-{arch}'), node_dir); os.remove('/tmp/node.tar.xz')
            for c in ['node', 'npm', 'npx']: os.path.exists(f := os.path.join(bin_dir, c)) and os.remove(f); os.symlink(os.path.join(node_bin, c), os.path.join(bin_dir, c))
            print("✓ node/npm")
        except Exception as e: print(f"✗ node: {e}")
    else: print("✓ node/npm")
    npm_cmd = npm_path if os.path.exists(npm_path) else 'npm'
    for cmd, pkg in [('codex', '@openai/codex'), ('claude', '@anthropic-ai/claude-code'), ('gemini', '@google/gemini-cli')]:
        if not _w(cmd):
            try: sp.run([npm_cmd, 'install', '-g', pkg], check=True, capture_output=True); print(f"✓ {cmd}")
            except: print(f"✗ {cmd}")
        else:
            print(f"✓ {cmd}")
    print("\n✅ Done! Restart terminal or run: export PATH=\"$HOME/.local/bin:$PATH\"")
# PROOT ISOLATED ENVIRONMENT - Test aio commands without affecting host
elif arg == 'proot':
    import platform as _platform
    _termux = os.environ.get('TERMUX_VERSION') is not None
    _proot_run = lambda cmd: sp.run(cmd, shell=True, capture_output=True, text=True)
    if _termux:
        _UDIR = '/data/data/com.termux/files/usr/var/lib/proot-distro/installed-rootfs/ubuntu'
        _check = lambda: shutil.which("proot-distro") is not None
        _ready = lambda: os.path.isdir(_UDIR)
        _install = lambda: _check() or sp.run(['pkg', 'install', '-y', 'proot-distro'], capture_output=True).returncode == 0
        _setup = lambda: _ready() or (print("⬇️  Installing Ubuntu...") or sp.run(['proot-distro', 'install', 'ubuntu'], capture_output=True).returncode == 0)
        _test = lambda: (r := sp.run(['proot-distro', 'login', 'ubuntu', '--', 'cat', '/etc/os-release'], capture_output=True, text=True)) and r.returncode == 0 and "Ubuntu" in r.stdout
        _teardown = lambda: sp.run(['proot-distro', 'remove', 'ubuntu'], capture_output=True).returncode == 0
        _shell_cmd = ["proot-distro", "login", "ubuntu"]
        _run_cmd = lambda args: ["proot-distro", "login", "ubuntu", "--"] + args
    else:
        _DIR, _FS = os.path.expanduser("~/.local/share/proot-ubuntu"), os.path.expanduser("~/.local/share/proot-ubuntu/rootfs")
        _check = lambda: shutil.which("proot") is not None
        _ready = lambda: os.path.exists(os.path.join(_FS, "bin/sh"))
        def _install():
            if _check(): return True
            bd = os.path.expanduser("~/.local/bin"); os.makedirs(bd, exist_ok=True); pb = os.path.join(bd, "proot")
            _proot_run(f"curl -sL https://proot.gitlab.io/proot/bin/proot -o {pb} && chmod +x {pb}"); return os.path.exists(pb)
        def _setup():
            os.makedirs(_FS, exist_ok=True)
            if _ready(): return True
            arch = "amd64" if _platform.machine() in ("x86_64", "AMD64") else "arm64"
            print(f"⬇️  Downloading Ubuntu 22.04 ({arch})..."); _proot_run(f"curl -sL https://cdimage.ubuntu.com/ubuntu-base/releases/22.04/release/ubuntu-base-22.04-base-{arch}.tar.gz | tar xz -C {_FS}"); return _ready()
        _test = lambda: (r := _proot_run(f"proot -r {_FS} -0 /bin/cat /etc/os-release")) and r.returncode == 0 and "Ubuntu" in r.stdout
        _teardown = lambda: os.path.exists(_DIR) and (shutil.rmtree(_DIR) or True)
        _shell_cmd = ["proot", "-r", _FS, "-0", "-w", "/root", "/bin/bash"]
        _run_cmd = lambda args: ["proot", "-r", _FS, "-0", "-w", "/root"] + args
    sub = work_dir_arg or "check"
    if sub == "check": print(f"proot: {'✓' if _check() else '✗'}  ubuntu: {'✓' if _ready() else '✗'}")
    elif sub == "install": print("OK" if _install() else "FAILED")
    elif sub == "setup": _check() or (_install() or _die("Install failed")); print("OK" if _setup() else "FAILED")
    elif sub == "test": print("OK" if _test() else "FAILED")
    elif sub == "shell": _ready() or _die("Run 'aio proot setup' first"); print("🐧 Entering Ubuntu...\n"); os.execvp(_shell_cmd[0], _shell_cmd)
    elif sub == "run":
        _ready() or _die("Run 'aio proot setup' first"); cmd_args = sys.argv[3:] if len(sys.argv) > 3 else []
        cmd_args or _die("Usage: aio proot run <command>"); os.execvp(_run_cmd(cmd_args)[0], _run_cmd(cmd_args))
    elif sub == "teardown": print("OK" if _teardown() else "NOTHING")
    else: print("aio proot [check|install|setup|test|shell|run|teardown] - Isolated Ubuntu for testing")
elif arg in ('backups', 'backup'):
    if not (backups := list_backups()): print("No backups found.")
    else:
        print(f"\n📦 Database Backups ({len(backups)} total)\n" + "━" * 70)
        [print(f"{i:2}. {os.path.basename(p)}\n    {s:,} bytes | {datetime.fromtimestamp(m).strftime('%Y-%m-%d %H:%M:%S')}") for i, (p, s, m) in enumerate(backups[-10:], 1)]
        print(f"\n📁 Location: {DATA_DIR}\n   Restore: aio restore <filename>")
elif arg == 'restore':
    if not work_dir_arg: print("Usage: aio restore <backup_filename>"); [print(f"  {os.path.basename(p)}") for p, _, _ in (list_backups() or [])[-5:]]; sys.exit(1)
    bp = os.path.join(DATA_DIR, work_dir_arg) if not os.path.isabs(work_dir_arg) else work_dir_arg
    if not os.path.exists(bp): _die(f"Backup not found: {bp}")
    if input(f"⚠️  Overwrite DB from {os.path.basename(bp)}? [y/N]: ").lower() != 'y': sys.exit(0)
    restore_database(bp); print("✅ Restored!")
elif arg == 'watch':
    work_dir_arg or _die("Usage: aio watch <session> [duration]\nPatterns: 'Are you sure?' -> y, 'Continue?' -> yes, '[y/N]' -> y")
    dur = int(sys.argv[3]) if len(sys.argv) > 3 else None
    print(f"👁 Watching '{work_dir_arg}'" + (f" for {dur}s" if dur else " (once)"))
    watch_tmux_session(work_dir_arg, {r'Are you sure\?': 'y', r'Continue\?': 'yes', r'\[y/N\]': 'y', r'\[Y/n\]': 'y'}, dur) or sys.exit(1)
elif arg == 'send':
    work_dir_arg or _die("Usage: aio send <session> <prompt> [--wait] [--no-enter]")
    prompt = ' '.join(a for a in sys.argv[3:] if a not in ('--wait', '--no-enter'))
    prompt or _die("No prompt provided")
    send_prompt_to_session(work_dir_arg, prompt, wait_for_completion='--wait' in sys.argv, timeout=60, send_enter='--no-enter' not in sys.argv) or sys.exit(1)
elif arg == 'multi':
    import json
    if work_dir_arg == 'set':  # aio multi set c:2 l:1
        ns = ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else ''
        if not ns: print(f"Current: {load_config().get('multi_default', 'c:3')}"); sys.exit(0)
        if not parse_agent_specs_and_prompt([''] + ns.split(), 1)[0]: _die(f"Invalid: {ns}  Format: c:N l:N g:N")
        with WALManager(DB_PATH) as c: c.execute("INSERT OR REPLACE INTO config VALUES ('multi_default', ?)", (ns,)); c.commit()
        print(f"✓ Default: {ns}"); sys.exit(0)
    project_path, start = (PROJECTS[int(work_dir_arg)], 3) if work_dir_arg and work_dir_arg.isdigit() and int(work_dir_arg) < len(PROJECTS) else (os.getcwd(), 2)
    agent_specs, task, used_default = parse_agent_specs_and_prompt(sys.argv, start)
    if not agent_specs:
        ds = load_config().get('multi_default', 'l:3'); agent_specs, _, _ = parse_agent_specs_and_prompt([''] + ds.split(), 1)
        print(f"Using: {ds}  (aio multi set <specs>)")
    feat_template = get_prompt('feat', show_location=True) or '{task}'
    if used_default:
        prompt = input_box(feat_template.format(task="<describe task>"), "Prompt (Ctrl+D run, Ctrl+C cancel)")
        if not (prompt := (prompt or '').strip()): sys.exit(0)
        task = prompt
    else: prompt = feat_template.format(task=task)

    total, repo_name, run_id = sum(c for _, c in agent_specs), os.path.basename(project_path), datetime.now().strftime('%Y%m%d-%H%M%S')
    session_name, run_dir = f"{repo_name}-{run_id}", os.path.join(WORKTREES_DIR, repo_name, run_id)
    candidates_dir = os.path.join(run_dir, "candidates"); os.makedirs(candidates_dir, exist_ok=True)
    with open(os.path.join(run_dir, "run.json"), "w") as f: json.dump({"task": task, "prompt": prompt, "agents": [f"{k}:{c}" for k, c in agent_specs], "created": run_id, "repo": project_path}, f, indent=2)
    with WALManager(DB_PATH) as c: c.execute("INSERT OR REPLACE INTO multi_runs VALUES (?, ?, ?, ?, 'running', CURRENT_TIMESTAMP, NULL)", (run_id, project_path, task, json.dumps([f"{k}:{c}" for k, c in agent_specs]))); c.commit()
    print(f"🚀 {total} agents + reviewer in {repo_name}/{run_id}..."); env, launched, agent_num, first = get_noninteractive_git_env(), [], {}, True
    for ak, cnt in agent_specs:
        bn, bc = sessions.get(ak, (None, None))
        if not bn: continue
        for i in range(cnt):
            agent_num[bn] = agent_num.get(bn, 0) + 1; wn, an = f"{bn}-{agent_num[bn]}", f"{ak}{i}"
            wt = os.path.join(candidates_dir, an); sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', f'wt-{repo_name}-{run_id}-{an}', wt], capture_output=True, env=env)
            if not os.path.exists(wt): continue
            sig, exit_signal = f"{session_name}-{wn}", f'; tmux wait-for -S {session_name}-{wn}'
            full_cmd = f'{bc} {shlex.quote(enhance_prompt(prompt, bn, wt))}{exit_signal}'
            sp.run(['tmux', 'new-session', '-d', '-s', session_name, '-n', wn, '-c', wt, full_cmd] if first else ['tmux', 'new-window', '-t', session_name, '-n', wn, '-c', wt, full_cmd], env=env); first = False
            sp.run(['tmux', 'split-window', '-h', '-t', f'{session_name}:{wn}', '-c', wt], env=env); sp.run(['tmux', 'select-pane', '-t', f'{session_name}:{wn}.0'], env=env)
            sp.run(['tmux', 'pipe-pane', '-t', f'{session_name}:{wn}.0', f'''sh -c 's=0;while IFS= read -r l;do [ $s -eq 1 ]&&continue;c=$(printf "%%s" "$l"|sed "s/\\x1b\\[[0-9;]*[a-zA-Z]//g");case "$c" in *"› "*|*"context left"*|*"> Type"*) tmux wait-for -S {sig};s=1;;esac;done' '''], env=env)
            launched.append((wn, bn, wt)); print(f"✓ {wn}")

    if not launched:
        print("✗ No agents created"); sys.exit(1)

    # Build reviewer prompt with context
    agents_str = ", ".join(f"{k}:{c}" for k, c in agent_specs)
    dirs_str = ", ".join(os.path.basename(p) for _, _, p in launched)
    prompt_template = get_prompt('reviewer', show_location=True) or "Review {DIRS} for: {TASK}"
    REVIEWER_PROMPT = prompt_template.format(TASK=prompt, AGENTS=agents_str, DIRS=dirs_str)
    # Add Ultrathink. prefix for Claude reviewer (increases thinking budget)
    REVIEWER_PROMPT = enhance_prompt(REVIEWER_PROMPT, 'claude')

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
elif arg == 'overnight' or arg == 'on':
    # Overnight autonomous work session with planning doc, live monitoring, and review
    # Usage: aio overnight [project#] - reads aio.md for requirements
    import json, re

    # Config: max candidates (default 5)
    max_candidates = int(config.get('overnight_max', '5'))

    # Determine project
    if work_dir_arg and work_dir_arg.isdigit():
        project_path = PROJECTS[int(work_dir_arg)] if int(work_dir_arg) < len(PROJECTS) else None
        if not project_path: print(f"✗ Invalid project index"); sys.exit(1)
    else:
        project_path = os.getcwd()

    # Find and read aio.md planning document
    aio_md = os.path.join(project_path, 'aio.md')
    if not os.path.exists(aio_md):
        print(f"📝 No aio.md found. Describe what you want the agents to build:")
        print(f"   (Be specific: what feature, what file, how to verify it works)")
        print()
        try:
            requirements = input("Requirements: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n✗ Cancelled"); sys.exit(0)
        if not requirements:
            print("✗ No requirements entered"); sys.exit(1)
        with open(aio_md, 'w') as f:
            f.write(f"# Requirements\n\n{requirements}\n")
        print(f"✓ Created {aio_md}\n")
    else:
        with open(aio_md) as f:
            requirements = f.read().strip()
        if not requirements:
            print(f"✗ aio.md is empty"); sys.exit(1)
        # Show requirements, offer edit if interactive
        print(f"📄 {aio_md}:\n" + "─" * 50)
        print('\n'.join(f"  {l}" for l in requirements.split('\n')[:10]))
        if requirements.count('\n') > 10: print(f"  ...")
        print("─" * 50)
        if sys.stdin.isatty():
            try:
                if input("[Enter=run, e=edit]: ").strip().lower() == 'e':
                    sp.run([os.environ.get('EDITOR', 'nvim'), aio_md])
                    with open(aio_md) as f: requirements = f.read().strip()
            except (EOFError, KeyboardInterrupt):
                print("\n✗ Cancelled"); sys.exit(0)

    # Parse agent specs from command line or use default
    agent_specs, _, _ = parse_agent_specs_and_prompt(sys.argv, 3 if work_dir_arg and work_dir_arg.isdigit() else 2)
    if not agent_specs:
        default_specs = config.get('overnight_agents', 'c:2 l:1')
        agent_specs, _, _ = parse_agent_specs_and_prompt([''] + default_specs.split(), 1)
        print(f"Using agents: {default_specs}  (change: aio config overnight_agents 'c:3 l:2')")

    total = min(sum(c for _, c in agent_specs), max_candidates)
    if total < sum(c for _, c in agent_specs):
        print(f"⚠ Limiting to {max_candidates} candidates (change: aio config overnight_max N)")
        # Trim agent_specs to fit
        new_specs, count = [], 0
        for k, c in agent_specs:
            take = min(c, max_candidates - count)
            if take > 0: new_specs.append((k, take))
            count += take
            if count >= max_candidates: break
        agent_specs = new_specs

    repo_name = os.path.basename(project_path)
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    session_name = f"{repo_name}-overnight-{run_id}"

    # Create run directory structure
    run_dir = os.path.join(WORKTREES_DIR, repo_name, f"overnight-{run_id}")
    candidates_dir = os.path.join(run_dir, "candidates")
    os.makedirs(candidates_dir, exist_ok=True)

    # Build comprehensive prompt from aio.md
    overnight_prompt = f"""You are working on an overnight autonomous session. Read and follow these requirements exactly:

{requirements}

WORKFLOW:
1. Read project files and understand the codebase
2. Run the project exactly as a user would to understand current behavior
3. Implement the requirements using library glue pattern (direct library calls, minimal custom logic)
4. Test thoroughly - run and verify output manually
5. Keep changes minimal and focused

CONSTRAINTS:
- Minimize line count while maintaining readability
- Use direct library calls (90%+ of code should be library calls)
- No polling - use event-based patterns only
- Set aggressive timeouts on all commands

When done, create DONE.md with:
- Summary of changes made
- Files modified
- How to verify: specific commands to run and expected output
- Any issues encountered"""

    # Save run info
    run_info = {"requirements": requirements, "prompt": overnight_prompt, "agents": [f"{k}:{c}" for k, c in agent_specs],
                "created": run_id, "repo": project_path, "max_candidates": max_candidates}
    with open(os.path.join(run_dir, "run.json"), "w") as f:
        json.dump(run_info, f, indent=2)

    # Copy aio.md to run directory for reference
    shutil.copy(aio_md, os.path.join(run_dir, "aio.md"))

    with WALManager(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO multi_runs VALUES (?, ?, ?, ?, 'overnight', CURRENT_TIMESTAMP, NULL)",
                    (f"overnight-{run_id}", project_path, requirements[:200], json.dumps([f"{k}:{c}" for k, c in agent_specs])))
        conn.commit()

    print(f"🌙 Starting overnight session: {repo_name}")
    print(f"   Requirements from: aio.md")
    print(f"   Candidates: {total} (max {max_candidates})")
    print(f"   Run dir: {run_dir}")

    env = get_noninteractive_git_env()
    launched = []
    agent_num = {}
    first_window = True
    escaped_prompt = shlex.quote(overnight_prompt)

    for agent_key, count in agent_specs:
        base_name, base_cmd = sessions.get(agent_key, (None, None))
        if not base_name: continue

        for i in range(count):
            agent_num[base_name] = agent_num.get(base_name, 0) + 1
            window_name = f"{base_name}-{agent_num[base_name]}"
            attempt_name = f"{agent_key}{i}"
            wt_path = os.path.join(candidates_dir, attempt_name)

            # Create worktree
            branch_name = f"wt-overnight-{repo_name}-{run_id}-{attempt_name}"
            sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', branch_name, wt_path], capture_output=True, env=env)
            if not os.path.exists(wt_path): continue

            # Copy aio.md to worktree
            shutil.copy(aio_md, os.path.join(wt_path, 'aio.md'))

            # Signal setup: send signal after command completes (simpler and more reliable than trap)
            signal_name = f"{session_name}-{window_name}"
            agent_prompt = enhance_prompt(overnight_prompt, base_name, wt_path)
            escaped_agent_prompt = shlex.quote(agent_prompt)
            # Run command then signal completion - no trap needed, works reliably
            full_cmd = f'{base_cmd} {escaped_agent_prompt}; tmux wait-for -S {signal_name}'

            if first_window:
                sp.run(['tmux', 'new-session', '-d', '-s', session_name, '-n', window_name, '-c', wt_path, f'bash -c {shlex.quote(full_cmd)}'], env=env)
                first_window = False
            else:
                sp.run(['tmux', 'new-window', '-t', session_name, '-n', window_name, '-c', wt_path, f'bash -c {shlex.quote(full_cmd)}'], env=env)

            # Split: agent left, bash right for manual intervention
            sp.run(['tmux', 'split-window', '-h', '-t', f'{session_name}:{window_name}', '-c', wt_path], env=env)
            sp.run(['tmux', 'select-pane', '-t', f'{session_name}:{window_name}.0'], env=env)

            launched.append((window_name, base_name, wt_path, signal_name))
            print(f"✓ {window_name} → {attempt_name}/")

    if not launched:
        print("✗ No agents created"); sys.exit(1)

    # Create signal watcher: sends tmux signals when DONE.md files appear, disables notifications
    # Map: candidate_dir:signal:window_name
    signal_map = ' '.join(f'{os.path.basename(p)}:{s}:{w}' for w, _, p, s in launched)
    watcher_script = f'''#!/bin/bash
# Watch for DONE.md files and send completion signals
declare -A sent
while true; do
    for triple in {signal_map}; do
        name="${{triple%%:*}}"
        rest="${{triple#*:}}"
        signal="${{rest%%:*}}"
        done_file="{candidates_dir}/$name/DONE.md"
        if [ -f "$done_file" ] && [ -z "${{sent[$name]}}" ]; then
            tmux wait-for -S "$signal" 2>/dev/null
            sent[$name]=1
            echo "$(date '+%H:%M:%S') ✓ $name done"
        fi
    done
    all_done=1
    for triple in {signal_map}; do
        name="${{triple%%:*}}"
        [ -z "${{sent[$name]}}" ] && all_done=0 && break
    done
    [ "$all_done" = "1" ] && echo "$(date '+%H:%M:%S') All complete!" && exit 0
    sleep 5
done'''
    sp.run(['tmux', 'new-window', '-t', session_name, '-n', 'watcher', '-c', candidates_dir, f'bash -c {shlex.quote(watcher_script)}'], env=env)

    # Create monitor window showing live diffs with actual code changes
    monitor_script = f'''#!/bin/bash
G=$'\\033[48;2;26;84;42m'; R=$'\\033[48;2;117;34;27m'; X=$'\\033[0m'
while true; do
    clear
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🌙 OVERNIGHT MONITOR - $(date '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    for d in {candidates_dir}/*/; do
        [ -d "$d" ] || continue
        name=$(basename "$d")
        done_file="$d/DONE.md"
        if [ -f "$done_file" ]; then
            echo "✅ $name: DONE"
            head -3 "$done_file" | sed 's/^/   /'
        else
            echo "🔄 $name:"
            cd "$d" 2>/dev/null || continue
            # Show changed files
            changed=$(git diff --name-only HEAD~1 2>/dev/null | head -3 | tr '\\n' ' ')
            [ -n "$changed" ] && echo "   files: $changed"
            # Show actual diff lines (max 6 per candidate)
            git diff HEAD~1 2>/dev/null | while IFS= read -r line; do
                case "$line" in
                    +*) [[ "$line" != "+++"* ]] && echo "   $G+${{line:1:70}}$X" ;;
                    -*) [[ "$line" != "---"* ]] && echo "   $R-${{line:1:70}}$X" ;;
                esac
            done | head -6
            more=$(git diff --stat HEAD~1 2>/dev/null | tail -1 | grep -oE '[0-9]+ insertion|[0-9]+ deletion' | tr '\\n' ' ')
            [ -n "$more" ] && echo "   ...$more"
        fi
        echo ""
    done
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    sleep 8
done'''
    sp.run(['tmux', 'new-window', '-t', session_name, '-n', '📊monitor', '-c', candidates_dir, f'bash -c {shlex.quote(monitor_script)}'], env=env)

    # Create review window (waits for all agents)
    review_prompt = f"""You are reviewing overnight work implementations.

TASK REQUIREMENTS (from aio.md):
{requirements}

CANDIDATES TO REVIEW: {', '.join(os.path.basename(p) for _, _, p, _ in launched)}

EVALUATION CRITERIA (in order of importance):
1. WORKS: Runs without errors, solves the stated problem
2. FAST: Equal or faster than original (MUST benchmark with `time` command)
3. LIBRARY GLUE: ~90%+ direct library calls, minimal custom logic
4. BRIEF: Shortest readable code wins
5. TIE-BREAKER: If line count similar, faster wins

REVIEW PROCESS:
1. For each candidate, cd into directory and run the code
2. BENCHMARK: Run `time python file.py` or `time ./script` to get ACTUAL execution time
3. Check DONE.md for their summary and verification steps
4. Count lines with `wc -l` for accurate line counts
5. Do NOT edit any code - only evaluate

CREATE REVIEW.md with:
# Overnight Review Results

## Summary
- Task: [brief description]
- Candidates evaluated: N
- Recommendation: [winner]

## Evaluation Matrix
| Candidate | Works | Time (real) | Library% | Lines | Score |
|-----------|-------|-------------|----------|-------|-------|
| c0        | YES   | 0.42s       | 85%      | 106   | 3/5   |

IMPORTANT: Speed column MUST show actual `time` output (e.g., "0.42s", "1.2s"), not subjective words like "Good" or "Fast".

## Detailed Analysis
### [candidate]: [PASS/FAIL]
- Benchmark: `time [command]` → real Xs, user Xs, sys Xs
- Verification: [commands run and results]
- Strengths: ...
- Issues: ...

## Human Review Steps
Run these commands to verify the winning solution:
```bash
cd [winner_dir]
[specific commands to test]
# Expected output: [what to look for]
```

## Recommendation
[Which candidate to merge and why]

Say REVIEW COMPLETE when done."""

    wait_cmds = '; '.join(f'echo "  ⏳ {w}..."; tmux wait-for {s}; echo "  ✅ {w}"' for w, _, _, s in launched)
    review_prompt_escaped = shlex.quote(enhance_prompt(review_prompt, 'claude'))
    wait_script = f'''echo "🌙 Overnight Review - Waiting for agents..."
echo ""
{wait_cmds}
echo ""
echo "✅ All agents complete. Starting review..."
sleep 2
claude --dangerously-skip-permissions {review_prompt_escaped}'''

    sp.run(['tmux', 'new-window', '-t', session_name, '-n', '📋review', '-c', candidates_dir, f'bash -c {shlex.quote(wait_script)}'], env=env)
    # Right pane: watch for REVIEW.md, open editor, then open shell in winner dir
    editor = os.environ.get('EDITOR', 'nvim')
    review_watcher = f'''echo "📄 Waiting for REVIEW.md..."
while [ ! -f "{candidates_dir}/REVIEW.md" ]; do sleep 2; done
echo "✅ Review complete!"
# Parse winner from REVIEW.md (looks for **c0** or **l0** pattern in Recommendation)
winner=$(grep -oE "\\*\\*[cl][0-9]+\\*\\*" "{candidates_dir}/REVIEW.md" | head -1 | tr -d '*')
if [ -n "$winner" ] && [ -d "{candidates_dir}/$winner" ]; then
    echo "🏆 Winner: $winner"
    echo "   Opening editor + shell in winner dir..."
    sleep 1
    # Open editor with REVIEW.md
    tmux split-window -v -t "{session_name}:📋review" -c "{candidates_dir}/$winner" "echo '🏆 Winner: $winner - ready to test/merge'; exec bash"
    {editor} "{candidates_dir}/REVIEW.md"
else
    echo "⚠ Could not detect winner, opening REVIEW.md"
    {editor} "{candidates_dir}/REVIEW.md"
fi'''
    sp.run(['tmux', 'split-window', '-h', '-t', f'{session_name}:📋review', '-c', candidates_dir, f'bash -c {shlex.quote(review_watcher)}'], env=env)

    # Select monitor window first
    sp.run(['tmux', 'select-window', '-t', f'{session_name}:📊monitor'], capture_output=True)
    ensure_tmux_options()
    sp.run(['tmux', 'set-option', '-t', session_name, 'status-right', '🌙 Overnight | 📊monitor | 📋review auto-starts'], capture_output=True)

    print(f"\n✅ Overnight session started: {session_name}")
    print(f"   📊 Monitor: live diff view")
    print(f"   📋 Review: auto-starts when all agents complete")
    print(f"   💤 Safe to detach (Ctrl+Q) and check tomorrow")
    print(f"\n   Attach later: aio attach")

    if "TMUX" in os.environ:
        print(f"   Switch: tmux switch-client -t {session_name}")
    else:
        os.execvp('tmux', ['tmux', 'attach', '-t', session_name])
elif arg == 'idea':
    # Idea gathering: agents use project as customer, identify top issue → ISSUES.md
    # Usage: aio idea [project#|path] [l:N] - defaults to cwd, l:3
    project_path = PROJECTS[int(work_dir_arg)] if work_dir_arg and work_dir_arg.isdigit() and int(work_dir_arg) < len(PROJECTS) else (work_dir_arg if work_dir_arg and os.path.isdir(work_dir_arg) else os.getcwd())
    agent_specs, _, _ = parse_agent_specs_and_prompt(sys.argv, 3 if work_dir_arg else 2)
    if not agent_specs: agent_specs = [('l', 3)]

    repo, run_id = os.path.basename(project_path), datetime.now().strftime('%Y%m%d-%H%M%S')
    session_name, issues_file = f"idea-{repo}-{run_id}", os.path.join(project_path, 'ISSUES.md')
    run_dir = os.path.join(WORKTREES_DIR, repo, f"idea-{run_id}")
    os.makedirs(run_dir, exist_ok=True)

    prompt = f'Ultrathink. 1) Use this project as customer 2) Find TOP issue 3) Write to {issues_file}\nFormat: ## Issue: title\\n**Severity**: high/med/low\\n### Repro\\n### Fix'

    print(f"💡 idea: {repo} → {issues_file}")
    env, first, base_cmd = get_noninteractive_git_env(), True, sessions.get('l', (None, None))[1]
    for i in range(sum(c for _, c in agent_specs if _ == 'l')):
        wt = os.path.join(run_dir, f"l{i}")
        sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', f'idea-{run_id}-l{i}', wt], capture_output=True, env=env)
        if not os.path.exists(wt): continue
        cmd = f'{base_cmd} {shlex.quote(prompt)}'
        (sp.run(['tmux', 'new-session', '-d', '-s', session_name, '-n', f'l{i}', '-c', wt, cmd], env=env) if first else sp.run(['tmux', 'new-window', '-t', session_name, '-n', f'l{i}', '-c', wt, cmd], env=env))
        first = False
        print(f"  ✓ l{i} → {wt}")

    if first: _die("No agents launched")
    ensure_tmux_options()
    print(f"📄 {issues_file}")
    os.execvp('tmux', ['tmux', 'attach', '-t', session_name]) if "TMUX" not in os.environ else print(f"tmux switch-client -t {session_name}")
elif arg == 'all':
    sequential = '--seq' in sys.argv or '--sequential' in sys.argv
    agent_specs, prompt, using_default = parse_agent_specs_and_prompt(sys.argv, 2)
    agent_specs or _die("Usage: aio all c:N l:N 'prompt'")
    total = sum(c for _, c in agent_specs) * len(PROJECTS)
    print(f"🌍 {total} agents across {len(PROJECTS)} projects {'(seq)' if sequential else '(parallel)'}")
    # Check auth for all projects
    auth_fails = []
    for i, p in enumerate(PROJECTS):
        if not os.path.exists(p) or _git(p, 'rev-parse', '--git-dir').returncode != 0: continue
        ok, fix = create_worktree(p, "", check_only=True)
        if not ok: auth_fails.append((i, os.path.basename(p), p, fix))
    if auth_fails:
        print(f"❌ Auth failed for {len(auth_fails)} projects:")
        for i, n, p, fix in auth_fails: print(f"  {n}: {fix or f'cd {p} && git remote set-url origin git@...'}")
        print("""
ℹ️  Fix: Switch remotes to SSH.
   • Works with aio's no-dialog approach
   • More secure than storing passwords

✅ After fixing, run 'aio all' again and all projects will work!""")
        sys.exit(1)
    print("✅ Auth OK\n")
    all_sess, proj_res, env = [], [], get_noninteractive_git_env()
    for pi, pp in enumerate(PROJECTS):
        pn = os.path.basename(pp)
        if not os.path.exists(pp): continue
        psess = []
        for ak, c in agent_specs:
            bn, bc = sessions.get(ak, (None, None))
            if not bn: continue
            for j in range(c):
                wn = f"{bn}-{datetime.now().strftime('%Y%m%d%H%M%S')}-p{pi}-{j}"
                wr = create_worktree(pp, wn)
                wp = wr[0] if wr else None
                if not wp: continue
                cmd = f'{bc} {shlex.quote(enhance_prompt(prompt, bn, wp))}'
                sn = os.path.basename(wp)
                create_tmux_session(sn, wp, cmd, env=env)
                psess.append((sn, bn, j+1, pn, wp)); print(f"✓ {bn}{j+1} {sn}")
        psess and all_sess.extend(psess) and proj_res.append((pi, pn, "LAUNCHED", psess))
    print(f"\n🎯 Launched {len(all_sess)} agents. Monitor: aio jobs")
elif arg == 'dash':
    sn = 'dash'
    if not sm.has_session(sn):
        sp.run(['tmux', 'new-session', '-d', '-s', sn, '-c', work_dir])
        sp.run(['tmux', 'split-window', '-h', '-t', sn, '-c', work_dir, 'bash -c "aio jobs; exec bash"'])
    os.execvp('tmux', ['tmux', 'attach', '-t', sn] if 'TMUX' not in os.environ else ['tmux', 'switch-client', '-t', sn])
elif arg == 'jobs':
    # Check for --running flag
    running_only = '--running' in sys.argv or '-r' in sys.argv
    list_jobs(running_only=running_only)
elif arg == 'attach':
    cwd = os.getcwd()
    def _attach(s): os.execvp('tmux', ['tmux', 'switch-client' if 'TMUX' in os.environ else 'attach', '-t', s])
    if WORKTREES_DIR in cwd:
        p = cwd.replace(WORKTREES_DIR + '/', '').split('/')
        if len(p) >= 2 and sm.has_session(s := f"{p[0]}-{p[1]}"): _attach(s)
    with WALManager(DB_PATH) as c: runs = c.execute("SELECT id, repo FROM multi_runs ORDER BY created_at DESC LIMIT 10").fetchall()
    if runs:
        for i, (rid, repo) in enumerate(runs): print(f"{i}. {'●' if sm.has_session(f'{os.path.basename(repo)}-{rid}') else '○'} {os.path.basename(repo)}-{rid}")
        ch = input("Select #: ").strip()
        if ch.isdigit() and int(ch) < len(runs): _attach(f"{os.path.basename(runs[int(ch)][1])}-{runs[int(ch)][0]}")
    print("No session")

elif arg in ['kill', 'killall']:
    if input("Kill all tmux sessions? (y/n): ").lower() in ['y', 'yes']:
        if 'TMUX' in os.environ: sp.run(['tmux', 'detach-client'])
        sp.run(['pkill', '-9', 'tmux']); print("✓ Killed all tmux")

elif arg == 'config':
    key, val = work_dir_arg, ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else None
    if not key: [print(f"  {k}: {v[:50]}{'...' if len(v)>50 else ''}") for k, v in sorted(config.items())]
    elif val:
        with WALManager(DB_PATH) as c: c.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (key, val)); c.commit()
        print(f"✓ {key}={val}")
    else: print(f"{key}: {config.get(key, '(not set)')}")

elif arg == 'prompt':
    # Edit prompts: aio prompt [name]
    name = work_dir_arg or 'feat'
    prompt_file = PROMPTS_DIR / f'{name}.txt'
    if not prompt_file.exists():
        print(f"📝 Prompts dir: {PROMPTS_DIR}")
        print(f"Available: {', '.join(p.stem for p in PROMPTS_DIR.glob('*.txt'))}")
        sys.exit(1)
    print(f"📝 Editing: {prompt_file}")
    current = prompt_file.read_text().strip()
    new_val = input_box(current, f"Edit '{name}' (Ctrl+D to save, Ctrl+C to cancel)")
    if new_val is None:
        print("Cancelled")
    elif new_val.strip() != current:
        prompt_file.write_text(new_val.strip())
        print(f"✓ Saved to {prompt_file}")
    else:
        print("No changes")

elif arg == 'gdrive':
    _rclone = shutil.which('rclone') or next((p for p in ['/usr/bin/rclone', '/usr/local/bin/rclone', os.path.expanduser('~/.local/bin/rclone')] if os.path.isfile(p)), None)
    if not _rclone and work_dir_arg == 'login':
        import platform; bd, arch = os.path.expanduser('~/.local/bin'), 'amd64' if platform.machine() in ('x86_64', 'AMD64') else 'arm64'
        print(f"Installing rclone to {bd}..."); os.makedirs(bd, exist_ok=True)
        if sp.run(f'curl -sL https://downloads.rclone.org/rclone-current-linux-{arch}.zip -o /tmp/rclone.zip && unzip -qjo /tmp/rclone.zip "*/rclone" -d {bd} && chmod +x {bd}/rclone && rm /tmp/rclone.zip', shell=True).returncode == 0:
            _rclone = f'{bd}/rclone'; print(f"✓ Installed {_rclone}")
        else: _die("rclone install failed")
    if work_dir_arg == 'login':
        _rclone or _die("rclone not found")
        if _rclone_configured():
            print(f"Already logged in as {_rclone_account() or 'unknown'}")
            if not _confirm("Switch to different account?"): sys.exit(0)
            sp.run([_rclone, 'config', 'delete', RCLONE_REMOTE])
        print("Opening Google Drive login..."); sp.run([_rclone, 'config', 'create', RCLONE_REMOTE, 'drive'])
        if _rclone_configured():
            _ok(f"Logged in as {_rclone_account() or 'unknown'}")
            r = sp.run([_rclone, 'lsf', f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}'], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                print("Found existing backup, pulling..."); _rclone_pull_notes(); _ok("Data restored")
            else:
                print("Creating backup folder..."); sp.run([_rclone, 'mkdir', f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}'], capture_output=True)
                _rclone_sync_data(wait=True); _ok("Backup initialized")
        else: _err("Login failed")
    elif work_dir_arg == 'logout':
        if _rclone_configured():
            sp.run([_rclone, 'config', 'delete', RCLONE_REMOTE]); _ok("Logged out")
        else: print("Not logged in")
    elif _rclone_configured():
        acct = _rclone_account()
        _ok(f"Logged in: {acct}" if acct else f"Configured ({RCLONE_REMOTE}:)")
        if _RCLONE_ERR_FILE.exists(): _err(f"Last sync failed:\n{_RCLONE_ERR_FILE.read_text().strip()}")
        print("Run 'aio gdrive logout' to switch accounts")
    else: _err("Not logged in. Run: aio gdrive login")

elif arg == 'sync':
    # Sync to gdrive: aio sync [agents|data|all]
    what = work_dir_arg or 'all'
    if not _rclone_configured(): _die("Not logged in. Run: aio gdrive login")
    if what in ('agents', 'all'): [sp.run(['rclone', 'copy', str(p), f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}/agents/{n}', '-u', '-P']) for n, p in _AGENT_DIRS.items() if p.exists()]
    if what in ('data', 'all'): sp.run(['rclone', 'sync', str(Path(SCRIPT_DIR) / 'data'), f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}', '-P'])

elif arg == 'note':
    # Notes: aio note [#|content] - number opens note, text creates note
    import re, threading
    NOTEBOOK_DIR = Path(SCRIPT_DIR) / 'data' / 'notebook'
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    def _note_slug(s): return re.sub(r'[^\w\-]', '', s.split('\n')[0][:40].lower().replace(' ', '-'))[:30] or 'note'
    def _note_preview(p): return p.read_text().split('\n')[0][:60]
    def _list_notes():
        notes = sorted(NOTEBOOK_DIR.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
        threading.Thread(target=_rclone_pull_notes, daemon=True).start()
        if not notes: print("No notes. Create: aio note <content>"); sys.exit(0)
        for i, n in enumerate(notes): print(f"{i}. {_note_preview(n)}")
        return notes
    raw = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    if not raw or raw == 'ls':  # List notes
        notes = _list_notes()
        if raw == 'ls': sys.exit(0)
        choice = input("View #: ").strip()
        notes = sorted(NOTEBOOK_DIR.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
        if choice.isdigit() and int(choice) < len(notes): print(f"\n{notes[int(choice)].read_text()}")
    elif raw.isdigit():  # Open note by number
        notes = sorted(NOTEBOOK_DIR.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
        if int(raw) < len(notes): print(notes[int(raw)].read_text())
        else: print(f"No note #{raw}"); _list_notes()
    else:  # Create note
        content = raw if raw.strip() else input_box('', 'Note (Ctrl+D save, Ctrl+C cancel)')
        if content:
            note_file = NOTEBOOK_DIR / f"{_note_slug(content)}-{datetime.now().strftime('%m%d%H%M')}.md"
            note_file.write_text(content); print(f"✓ {_note_preview(note_file)}")
            started, _ = _rclone_sync_data()
            print("☁ Syncing..." if started else "💡 Run 'aio gdrive login' for cloud backup")
        else: print("Cancelled")

elif arg == 'r' or arg == 'review':
    # Review mode: add reviewer window to existing session
    import json
    force_latest = (arg == 'r')

    def run_dir_exists(rid, repo):
        return os.path.isdir(os.path.join(WORKTREES_DIR, os.path.basename(repo), rid))

    # Find run to review
    run_repo = None
    if work_dir_arg:
        run_id = work_dir_arg
        with WALManager(DB_PATH) as conn:
            row = conn.execute("SELECT repo FROM multi_runs WHERE id = ?", (run_id,)).fetchone()
            if row: run_repo = row[0]
    else:
        with WALManager(DB_PATH) as conn:
            all_runs = conn.execute("SELECT id, repo, prompt, status, created_at FROM multi_runs ORDER BY created_at DESC").fetchall()
        if not all_runs:
            print("No runs to review. Use 'aio multi' first.")
            sys.exit(0)
        # Check for stale entries and offer removal
        stale_ids = [r[0] for r in all_runs if not run_dir_exists(r[0], r[1])]
        if stale_ids and not force_latest and input(f"⚠️  {len(stale_ids)} runs cleaned up. Remove from list? [y/N]: ").strip().lower() == 'y':
            with WALManager(DB_PATH) as conn:
                conn.execute(f"DELETE FROM multi_runs WHERE id IN ({','.join('?'*len(stale_ids))})", stale_ids)
                conn.commit()
            all_runs = [r for r in all_runs if r[0] not in stale_ids]
            print(f"✓ Removed {len(stale_ids)} stale entries")
        runs = all_runs[:10]
        if not runs:
            print("No runs left to review.")
            sys.exit(0)
        if force_latest:
            run_id, run_repo = runs[0][0], runs[0][1]
            print(f"📋 Force reviewing: {runs[0][2][:50]}...")
        else:
            print("Recent runs:")
            for i, (rid, repo, prompt, status, created_at) in enumerate(runs):
                elapsed, exists = "", "✓" if run_dir_exists(rid, repo) else "✗"
                if created_at:
                    try:
                        mins = int((datetime.now() - datetime.fromisoformat(created_at)).total_seconds() / 60)
                        elapsed = f"{mins}m" if mins < 60 else f"{mins//60}h{mins%60}m"
                    except: pass
                print(f"  {i}. {exists} [{status}] {elapsed:>5} {rid} - {os.path.basename(repo)}: {prompt[:40]}...")
            choice = input("Select #: ").strip()
            idx = int(choice) if choice.isdigit() and int(choice) < len(runs) else None
            run_id = runs[idx][0] if idx is not None else choice
            run_repo = runs[idx][1] if idx is not None else None

    # Find run directory
    run_dir = os.path.join(WORKTREES_DIR, os.path.basename(run_repo), run_id) if run_repo else None
    if not run_dir or not os.path.isdir(run_dir):
        expected = run_dir or f"{WORKTREES_DIR}/*/{run_id}"
        print(f"✗ Run cleaned up: {run_id}\n   Was at: {expected}")
        sys.exit(1)
    repo_name = os.path.basename(run_repo)
    candidates_dir = os.path.join(run_dir, "candidates")

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

    prompt_template = get_prompt('reviewer', show_location=True) or "Review the code in {DIRS} for task: {TASK}"
    REVIEWER_PROMPT = prompt_template.format(TASK=task, AGENTS=agents, DIRS=dirs)
    # Add Ultrathink. prefix for Claude reviewer (increases thinking budget)
    REVIEWER_PROMPT = enhance_prompt(REVIEWER_PROMPT, 'claude')
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

    wts = [d for d in os.listdir(WORKTREES_DIR) if os.path.isdir(os.path.join(WORKTREES_DIR, d))] if os.path.exists(WORKTREES_DIR) else []
    with WALManager(DB_PATH) as c: db_cnt = c.execute("SELECT COUNT(*) FROM multi_runs").fetchone()[0]
    if not wts and not db_cnt: print("Nothing to clean"); sys.exit(0)
    print(f"Will delete: {len(wts)} dirs, {db_cnt} db entries")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").strip().lower() in ['y', 'yes']) or _die("✗")
    for wt in wts:
        try: shutil.rmtree(os.path.join(WORKTREES_DIR, wt)); print(f"✓ {wt}")
        except: pass
    for p in PROJECTS: os.path.exists(p) and _git(p, 'worktree', 'prune')
    with WALManager(DB_PATH) as c: c.execute("DELETE FROM multi_runs"); c.commit()
    print("✓ Cleaned")
elif arg == 'p':
    if PROJECTS:
        print("📁 PROJECTS:")
        for i, proj in enumerate(PROJECTS):
            exists = "✓" if os.path.exists(proj) else "✗"
            print(f"  {i}. {exists} {proj}")

    if APPS:
        if PROJECTS:
            print("")  # Add blank line between sections
        print("⚡ COMMANDS:")
        for i, (app_name, app_cmd) in enumerate(APPS):
            cmd_display = format_app_command(app_cmd)
            print(f"  {len(PROJECTS) + i}. {app_name} → {cmd_display}")
elif arg == 'add':
    # Unified add: project (path) or command (name + shell string)
    # aio add                    → add cwd as project
    # aio add ~/path             → add path as project
    # aio add name "cmd"         → add command
    # aio add python script.py   → prompt for name (detects interpreter)
    args = sys.argv[2:]
    is_global = '--global' in args
    args = [a for a in args if a != '--global']

    # Detect command: 2+ args where first isn't a valid directory
    if len(args) >= 2 and not os.path.isdir(os.path.expanduser(args[0])):
        # Check if first arg is an interpreter (python, node, etc.) - prompt for name
        interpreters = ['python', 'python3', 'node', 'npm', 'ruby', 'perl', 'java', 'go', 'sh', 'bash', 'npx']
        if args[0] in interpreters:
            cmd_val = ' '.join(args)  # whole thing is the command
            print(f"Command: {cmd_val}")
            cmd_name = input("Name for this command: ").strip()
            if not cmd_name: print("✗ Cancelled"); sys.exit(1)
        else:
            cmd_name, cmd_val = args[0], ' '.join(args[1:])
        if cmd_val.startswith('[') and cmd_val.endswith(']'): cmd_val = cmd_val[1:-1]
        cwd, home = os.getcwd(), os.path.expanduser('~')
        if not is_global and cwd != home and not cmd_val.startswith('cd '):
            cmd_val = f"cd {cwd.replace(home, '~')} && {cmd_val}"
            print(f"📍 Context: {cwd.replace(home, '~')}")
        existing = {n.lower(): n for n, _ in load_apps()}
        if cmd_name.lower() in existing:
            print(f"✗ '{existing[cmd_name.lower()]}' exists. Use: aio cmd edit {cmd_name}"); sys.exit(1)
        ok, msg = add_app(cmd_name, cmd_val)
        print(f"{'✓' if ok else '✗'} {msg}")
        if ok: auto_backup_check(); list_all_items()
        sys.exit(0 if ok else 1)

    # Adding project
    path = os.path.abspath(os.path.expanduser(args[0])) if args else os.getcwd()
    ok, msg = add_project(path)
    print(f"{'✓' if ok else '✗'} {msg}")
    if ok: auto_backup_check(); list_all_items()
    sys.exit(0 if ok else 1)

elif arg == 'remove' or arg == 'rm':
    # Unified remove: by number or name
    # aio remove      → show list
    # aio remove 0    → remove item #0 (project or app by unified index)
    # aio remove name → remove app by name
    if not work_dir_arg:
        print("Usage: aio remove <#|name>\n"); list_all_items(); sys.exit(0)

    projects, apps = load_projects(), load_apps()
    target = work_dir_arg

    if target.isdigit():
        idx = int(target)
        if idx < len(projects):
            ok, msg = remove_project(idx)
        elif idx < len(projects) + len(apps):
            ok, msg = remove_app(idx - len(projects))
        else:
            print(f"✗ Invalid index: {idx}"); list_all_items(); sys.exit(1)
    else:
        # By name (apps only)
        app_idx = next((i for i, (n, _) in enumerate(apps) if n.lower() == target.lower()), None)
        if app_idx is None:
            print(f"✗ Not found: {target}"); list_all_items(); sys.exit(1)
        ok, msg = remove_app(app_idx)

    print(f"{'✓' if ok else '✗'} {msg}")
    if ok: auto_backup_check(); list_all_items()
    sys.exit(0 if ok else 1)

elif arg in ('cmd', 'command', 'commands', 'app', 'apps'):
    # Command management (aio cmd [list|add|edit|rm])
    sub = work_dir_arg
    if not sub or sub == 'list':
        list_all_items()
    elif sub == 'add':
        os.execvp(sys.executable, [sys.executable, __file__, 'add'] + sys.argv[3:])
    elif sub in ('rm', 'remove', 'delete'):
        os.execvp(sys.executable, [sys.executable, __file__, 'remove'] + sys.argv[3:])
    elif sub == 'edit':
        cmd_id = sys.argv[3] if len(sys.argv) > 3 else None
        if not cmd_id: print("✗ Usage: aio cmd edit <#|name>"); sys.exit(1)
        projects, apps = load_projects(), load_apps()
        cmd_name = cmd_val = None
        if cmd_id.isdigit():
            idx = int(cmd_id) - len(projects)
            if 0 <= idx < len(apps): cmd_name, cmd_val = apps[idx]
        else:
            match = next(((n, c) for n, c in apps if n.lower() == cmd_id.lower()), None)
            if match: cmd_name, cmd_val = match
        if not cmd_name: print(f"✗ Command not found: {cmd_id}"); sys.exit(1)
        print(f"Editing: {cmd_name}\nCurrent: {format_app_command(cmd_val)}")
        new_cmd = input("New command (Enter=keep): ").strip()
        if new_cmd:
            with WALManager(DB_PATH) as conn:
                conn.execute("UPDATE apps SET command = ? WHERE name = ?", (new_cmd, cmd_name)); conn.commit()
            print(f"✓ Updated: {cmd_name}"); auto_backup_check()
        else:
            print("No changes")
    else:
        print(f"✗ Unknown: {sub}\nUse: aio cmd [list|add|edit|rm]")

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
elif arg == 'e':
    if 'TMUX' in os.environ:
        os.execvp('nvim', ['nvim', '.', '-c', 'nmap <LeftMouse> <LeftMouse><CR>'])
    else:
        create_tmux_session('edit', os.getcwd(), 'nvim . -c "nmap <LeftMouse> <LeftMouse><CR>"')
        os.execvp('tmux', ['tmux', 'attach', '-t', 'edit'])
elif arg == 'x':
    sp.run(['tmux', 'kill-server'])
    print("✓ All sessions killed")
elif arg == 'push':
    cwd = os.getcwd(); ensure_git_config(); skip = '--yes' in sys.argv or '-y' in sys.argv
    r = _git(cwd, 'rev-parse', '--git-dir')
    r.returncode == 0 or _die("✗ Not a git repository")
    is_wt = '.git/worktrees/' in r.stdout.strip() or cwd.startswith(WORKTREES_DIR)
    args = [a for a in sys.argv[2:] if a not in ['--yes', '-y']]
    target = args[0] if args and os.path.exists(os.path.join(cwd, args[0])) else None
    if target: args = args[1:]
    msg = ' '.join(args) if args else (f"Update {target}" if target else f"Update {os.path.basename(cwd)}")
    env = get_noninteractive_git_env()

    if is_wt:
        wt_name, proj = os.path.basename(cwd), get_project_for_worktree(cwd)
        proj or _die(f"✗ Could not find project for {wt_name}")
        wt_branch = _git(cwd, 'branch', '--show-current').stdout.strip()
        print(f"\n📍 Worktree: {wt_name} | Branch: {wt_branch} | Msg: {msg}")
        to_main = skip or input("Push to: 1=main 2=branch [1]: ").strip() != '2'
        _git(cwd, 'add', target) if target else _git(cwd, 'add', '-A')
        r = _git(cwd, 'commit', '-m', msg)
        r.returncode == 0 and print(f"✓ Committed: {msg}")
        if to_main:
            main = _git_main(proj)
            _git(proj, 'checkout', main).returncode == 0 or _die(f"✗ Checkout {main} failed")
            _git(proj, 'merge', wt_branch, '--no-edit', '-X', 'theirs').returncode == 0 or _die("✗ Merge failed")
            print(f"✓ Merged {wt_branch} → {main}")
            _git_push(proj, main, env) or sys.exit(1)
            _git(proj, 'fetch', 'origin', env=env); _git(proj, 'reset', '--hard', f'origin/{main}')
            if not skip and input(f"\nDelete worktree '{wt_name}'? (y/n): ").strip().lower() in ['y', 'yes']:
                _git(proj, 'worktree', 'remove', '--force', cwd); _git(proj, 'branch', '-D', f'wt-{wt_name}')
                os.path.exists(cwd) and shutil.rmtree(cwd); print("✓ Cleaned up worktree")
                os.chdir(proj); os.execvp(os.environ.get('SHELL', 'bash'), [os.environ.get('SHELL', 'bash')])
        else:
            r = _git(cwd, 'push', '-u', 'origin', wt_branch, env=env)
            print(f"✓ Pushed to {wt_branch}") if r.returncode == 0 else _die(f"✗ Push failed: {r.stderr.strip()}")
    else:
        cur = _git(cwd, 'branch', '--show-current').stdout.strip()
        main = _git_main(cwd)
        _git(cwd, 'add', target) if target else _git(cwd, 'add', '-A')
        r = _git(cwd, 'commit', '-m', msg)
        if r.returncode == 0: print(f"✓ Committed: {msg}")
        elif 'nothing to commit' in r.stdout:
            if work_dir_arg and _git(cwd, 'commit', '--allow-empty', '-m', msg).returncode == 0: print(f"✓ Empty commit: {msg}")
            else: print("ℹ No changes"); sys.exit(0)
        else: _die(f"✗ Commit failed: {r.stderr.strip() or r.stdout.strip()}")
        if cur != main:
            _git(cwd, 'checkout', main).returncode == 0 or _die(f"✗ Checkout failed")
            _git(cwd, 'merge', cur, '--no-edit', '-X', 'theirs').returncode == 0 or _die("✗ Merge failed")
            print(f"✓ Merged {cur} → {main}")
        _git(cwd, 'fetch', 'origin', env=env)
        _git_push(cwd, main, env) or sys.exit(1)
elif arg == 'pull':
    cwd = os.getcwd(); _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("✗ Not a git repo")
    env = get_noninteractive_git_env(); _git(cwd, 'fetch', 'origin', env=env)
    ref = 'origin/main' if _git(cwd, 'rev-parse', '--verify', 'origin/main').returncode == 0 else 'origin/master'
    info = _git(cwd, 'log', '-1', '--format=%h %s', ref).stdout.strip()
    print(f"⚠ DELETE local changes → {info}")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").strip().lower() in ['y', 'yes']) or _die("✗ Cancelled")
    _git(cwd, 'reset', '--hard', ref); _git(cwd, 'clean', '-f', '-d'); print(f"✓ Synced: {info}")
elif arg == 'revert':
    cwd = os.getcwd(); _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("✗ Not a git repo")
    n = int(work_dir_arg) if work_dir_arg and work_dir_arg.isdigit() else 1
    r = _git(cwd, 'revert', 'HEAD', '--no-edit') if n == 1 else _git(cwd, 'revert', f'HEAD~{n}..HEAD', '--no-edit')
    print(f"✓ Reverted {n} commit(s)") if r.returncode == 0 else _die(f"✗ Revert failed: {r.stderr.strip()}")
elif arg == 'setup':
    cwd = os.getcwd()
    if not os.path.isdir(os.path.join(cwd, '.git')): _git(cwd, 'init', '-b', 'main'); print("✓ Initialized")
    else: print("ℹ Already a git repo")
    if _git(cwd, 'rev-parse', 'HEAD').returncode != 0:
        _git(cwd, 'add', '-A')
        if _git(cwd, 'diff', '--cached', '--quiet').returncode == 0:
            Path(os.path.join(cwd, '.gitignore')).touch(); _git(cwd, 'add', '.gitignore')
        _git(cwd, 'commit', '-m', 'Initial commit'); print("✓ Initial commit")
    _git(cwd, 'branch', '-M', 'main')
    has_remote = _git(cwd, 'remote', 'get-url', 'origin').returncode == 0
    url = work_dir_arg
    if not url and not has_remote and shutil.which('gh'):
        name = os.path.basename(cwd)
        resp = input(f"🚀 Create GitHub repo '{name}'? (y/n/private): ").strip().lower()
        if resp in ['y', 'yes', 'p', 'private']:
            vis = '--private' if resp in ['p', 'private'] else '--public'
            r = sp.run(['gh', 'repo', 'create', name, vis], capture_output=True, text=True, timeout=30)
            if r.returncode != 0 and 'already exists' in r.stderr.lower():
                input("Repo exists. Connect? (y/n): ").strip().lower() in ['y', 'yes'] or _die("✗ Cancelled")
            user = sp.run(['gh', 'api', 'user', '-q', '.login'], capture_output=True, text=True).stdout.strip()
            url = r.stdout.strip() or f"https://github.com/{user}/{name}.git"
            print("✓ Created/connected repo")
        else: _die("✗ Cancelled")
    if not url and not has_remote:
        url = input("Enter remote URL (Enter to skip): ").strip()
        if not url: print("Add later: git remote add origin <url>"); sys.exit(0)
    if url:
        _git(cwd, 'remote', 'set-url' if has_remote else 'remote', 'add', 'origin', url) if has_remote else _git(cwd, 'remote', 'add', 'origin', url)
        print(f"✓ Remote: {url}")
    env = get_noninteractive_git_env()
    r = _git(cwd, 'push', '-u', 'origin', 'main', env=env)
    print("✓ Pushed" if r.returncode == 0 else "ℹ Push skipped")
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

            # Send agent prefix in background (user can continue typing)
            prefix = get_agent_prefix(base_name, worktree_path)
            if prefix:
                sp.Popen([sys.executable, __file__, 'send', session_name, prefix, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

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
elif arg and os.path.isfile(arg):
    ext = os.path.splitext(arg)[1].lower()
    if ext == '.py': os.execvp(sys.executable, [sys.executable, arg] + sys.argv[2:])
    elif ext in ('.html', '.htm'): __import__('webbrowser').open('file://' + os.path.abspath(arg)); sys.exit(0)
    elif ext == '.md': os.execvp(os.environ.get('EDITOR', 'nvim'), [os.environ.get('EDITOR', 'nvim'), arg])
else:
    # GHOST SESSION CLAIMING - Try to use pre-warmed agent for instant startup
    # If user ran 'aio 0' earlier, ghosts are waiting. Claim one for instant response.
    if arg in _GHOST_MAP and not work_dir_arg:  # Simple agent command (c/l/g/o)
        ghost = _ghost_claim(arg, work_dir)
        if ghost:
            print(f"⚡ Ghost claimed - instant startup!")
            # Rename ghost to proper session name and attach
            agent_name = sessions[arg][0] if arg in sessions else arg
            session_name = f"{agent_name}-{os.path.basename(work_dir)}"
            sp.run(['tmux', 'rename-session', '-t', ghost, session_name], capture_output=True)
            if 'TMUX' in os.environ:
                launch_in_new_window(session_name)
            else:
                cmd = sm.attach(session_name)
                os.execvp(cmd[0], cmd)
            sys.exit(0)
        # No ghost available - fall through to normal flow (fresh spawn)

    # If inside tmux and arg is simple agent key (c/l/g), create pane instead of session
    if 'TMUX' in os.environ and arg in sessions and len(arg) == 1:
        agent_name, cmd = sessions[arg]
        sp.run(['tmux', 'split-window', '-bv', '-c', work_dir, cmd])
        prefix = get_agent_prefix(agent_name, work_dir)
        if prefix:
            time.sleep(0.5)  # Wait for pane to initialize
            sp.run(['tmux', 'send-keys', '-t', '!', '-l', prefix])
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
        # Custom prompt provided - spawn aio send in background (non-blocking)
        prompt = ' '.join(prompt_parts)
        print(f"📤 Prompt queued (will send when agent ready)")
        cmd = [sys.executable, __file__, 'send', session_name, prompt]
        if is_single_p_session:
            cmd.append('--no-enter')
        sp.Popen(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif is_single_p_session:
        # Single-p session without custom prompt - insert default prompt without running
        prompt_map = {'cp': CODEX_PROMPT, 'lp': CLAUDE_PROMPT, 'gp': GEMINI_PROMPT}
        default_prompt = prompt_map.get(arg, '')
        if default_prompt:
            print(f"📝 Prompt queued (inserting when agent ready)")
            sp.Popen([sys.executable, __file__, 'send', session_name, default_prompt, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif arg in sessions:
        # Session without prompt - insert agent prefix (user can continue typing)
        agent_name = sessions[arg][0]
        prefix = get_agent_prefix(agent_name, work_dir)
        if prefix:
            sp.Popen([sys.executable, __file__, 'send', session_name, prefix, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

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
