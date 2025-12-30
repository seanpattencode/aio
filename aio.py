#!/usr/bin/env python3
# aio - AI agent session manager (compact version)
import os, sys, subprocess as sp, json, sqlite3, shlex, shutil, time, atexit, re
from datetime import datetime
from pathlib import Path

_START, _CMD = time.time(), ' '.join(sys.argv[1:3]) if len(sys.argv) > 1 else 'help'
def _save_timing():
    try: d = os.path.expanduser("~/.local/share/aios"); os.makedirs(d, exist_ok=True); open(f"{d}/timing.jsonl", "a").write(json.dumps({"cmd": _CMD, "ms": int((time.time() - _START) * 1000), "ts": datetime.now().isoformat()}) + "\n")
    except: pass
atexit.register(_save_timing)

# Helpers
def _git(path, *args, **kw): return sp.run(['git', '-C', path] + list(args), capture_output=True, text=True, **kw)
def _tmux(args): return sp.run(['tmux'] + args, capture_output=True, text=True)
def _ok(msg): print(f"✓ {msg}")
def _err(msg): print(f"✗ {msg}")
def _die(msg, code=1): _err(msg); sys.exit(code)
def _confirm(msg): return input(f"{msg} (y/n): ").strip().lower() in ['y', 'yes']

_pexpect, _prompt_toolkit = None, None
def _get_pexpect():
    global _pexpect
    if _pexpect is None:
        try: import pexpect as _p; _pexpect = _p
        except: _pexpect = False
    return _pexpect if _pexpect else None

def _get_prompt_toolkit():
    global _prompt_toolkit
    if _prompt_toolkit is None:
        try:
            from prompt_toolkit import Application
            from prompt_toolkit.layout import Layout
            from prompt_toolkit.widgets import TextArea, Frame
            from prompt_toolkit.key_binding import KeyBindings
            _prompt_toolkit = {'Application': Application, 'Layout': Layout, 'TextArea': TextArea, 'Frame': Frame, 'KeyBindings': KeyBindings}
        except: _prompt_toolkit = False
    return _prompt_toolkit if _prompt_toolkit else None

def ensure_deps(skip_check=False):
    if skip_check: return
    missing = [c for c in ['tmux', 'claude'] if not shutil.which(c)]
    if missing: print(f"⚠ Missing: {', '.join(missing)}. Run: aio install"); sys.exit(1)

def input_box(prefill="", title="Ctrl+D to run, Ctrl+C to cancel"):
    pt = _get_prompt_toolkit()
    if not sys.stdin.isatty() or 'TMUX' in os.environ or not pt:
        print(f"[{title}] " if not prefill else f"[{title}]\n{prefill}\n> ", end="", flush=True)
        try: return input() if not prefill else prefill
        except: print("\nCancelled"); return None
    kb, cancelled = pt['KeyBindings'](), [False]
    @kb.add('c-d')
    def _(e): e.app.exit()
    @kb.add('c-c')
    def _(e): cancelled[0] = True; e.app.exit()
    ta = pt['TextArea'](text=prefill, multiline=True, focus_on_click=True)
    pt['Application'](layout=pt['Layout'](pt['Frame'](ta, title=title)), key_bindings=kb, full_screen=True, mouse_support=True).run()
    return None if cancelled[0] else ta.text

# Session Manager
class TmuxManager:
    def __init__(self): self._ver = None
    def new_session(self, n, d, c, e=None): return sp.run(['tmux', 'new-session', '-d', '-s', n, '-c', d] + ([c] if c else []), capture_output=True, env=e)
    def send_keys(self, n, t): return sp.run(['tmux', 'send-keys', '-l', '-t', n, t])
    def attach(self, n): return ['tmux', 'attach', '-t', n]
    def has_session(self, n):
        try: return sp.run(['tmux', 'has-session', '-t', n], capture_output=True, timeout=2).returncode == 0
        except sp.TimeoutExpired: return (sp.run(['pkill', '-9', 'tmux']), False)[1] if input("⚠ tmux hung. Kill? (y/n): ").lower() == 'y' else sys.exit(1)
    def list_sessions(self): return _tmux(['list-sessions', '-F', '#{session_name}'])
    def capture(self, n): return _tmux(['capture-pane', '-p', '-t', n])
    @property
    def version(self):
        if self._ver is None: self._ver = sp.check_output(['tmux', '-V'], text=True).split()[1] if shutil.which('tmux') else '0'
        return self._ver

sm = TmuxManager()

# Paths and constants
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROMPTS_DIR = Path(SCRIPT_DIR) / 'data' / 'prompts'
DATA_DIR = os.path.expanduser("~/.local/share/aios")
DB_PATH = os.path.join(DATA_DIR, "aio.db")
_GHOST_PREFIX, _GHOST_TIMEOUT = '_aio_ghost_', 300
_GHOST_MAP = {'c': 'c', 'l': 'l', 'g': 'g', 'o': 'l', 'cp': 'c', 'lp': 'l', 'gp': 'g'}
RCLONE_REMOTE, RCLONE_BACKUP_PATH = 'aio-gdrive', 'aio-backup'
_AGENT_DIRS = {'claude': Path.home()/'.claude', 'codex': Path.home()/'.codex', 'gemini': Path.home()/'.gemini'}
_TMUX_CONF, _AIO_MARKER = os.path.expanduser('~/.tmux.conf'), '# aio-managed-config'

# Git helpers
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

def get_noninteractive_git_env():
    env = os.environ.copy()
    env.pop('DISPLAY', None); env.pop('GPG_AGENT_INFO', None)
    env['GIT_TERMINAL_PROMPT'], env['SSH_ASKPASS'], env['GIT_ASKPASS'] = '0', '', ''
    return env

# Update checking
def manual_update():
    r = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', '--git-dir'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    if r.returncode != 0: print("✗ Not in a git repository"); return False
    print("🔄 Checking for updates...")
    before = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', 'HEAD'], capture_output=True, text=True)
    if before.returncode != 0: print("✗ Failed to get current version"); return False
    before_hash = before.stdout.strip()[:8]
    if sp.run(['git', '-C', SCRIPT_DIR, 'fetch'], capture_output=True, text=True).returncode != 0: return False
    status = sp.run(['git', '-C', SCRIPT_DIR, 'status', '-uno'], capture_output=True, text=True)
    if 'Your branch is behind' not in status.stdout: print(f"✓ Already up to date ({before_hash})"); return True
    print("⬇️  Downloading updates...")
    if sp.run(['git', '-C', SCRIPT_DIR, 'pull', '--ff-only'], capture_output=True, text=True).returncode != 0: return False
    after = sp.run(['git', '-C', SCRIPT_DIR, 'rev-parse', 'HEAD'], capture_output=True, text=True)
    if after.returncode == 0: print(f"✅ Updated: {before_hash} → {after.stdout.strip()[:8]}")
    return True

def check_for_updates_warning():
    ts_file = os.path.join(DATA_DIR, '.update_check')
    if os.path.exists(ts_file) and time.time() - os.path.getmtime(ts_file) < 1800: return
    if not hasattr(os, 'fork') or os.fork() != 0: return
    try:
        Path(ts_file).touch()
        r = sp.run(['git', '-C', SCRIPT_DIR, 'fetch', '--dry-run'], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stderr.strip(): Path(os.path.join(DATA_DIR, '.update_available')).touch()
    except: pass
    os._exit(0)

def show_update_warning():
    marker = os.path.join(DATA_DIR, '.update_available')
    if os.path.exists(marker):
        r = sp.run(['git', '-C', SCRIPT_DIR, 'status', '-uno'], capture_output=True, text=True)
        if 'Your branch is behind' in r.stdout: print("⚠️  Update available! Run 'aio update'")
        else:
            try: os.remove(marker)
            except: pass

def ensure_git_config():
    name, email = sp.run(['git', 'config', 'user.name'], capture_output=True, text=True), sp.run(['git', 'config', 'user.email'], capture_output=True, text=True)
    if name.returncode == 0 and email.returncode == 0 and name.stdout.strip() and email.stdout.strip(): return True
    if not shutil.which('gh'): return False
    try:
        r = sp.run(['gh', 'api', 'user'], capture_output=True, text=True)
        if r.returncode != 0: return False
        user = json.loads(r.stdout)
        gh_name, gh_login = user.get('name') or user.get('login', ''), user.get('login', '')
        gh_email = user.get('email') or f"{gh_login}@users.noreply.github.com"
        if gh_name and not name.stdout.strip(): sp.run(['git', 'config', '--global', 'user.name', gh_name], capture_output=True)
        if gh_email and not email.stdout.strip(): sp.run(['git', 'config', '--global', 'user.email', gh_email], capture_output=True)
        return True
    except: return False

# Database
class WALManager:
    def __init__(self, db_path): self.db_path, self.conn = db_path, None
    def __enter__(self): self.conn = sqlite3.connect(self.db_path); self.conn.execute("PRAGMA journal_mode=WAL;"); return self.conn
    def __exit__(self, *args): self.conn and self.conn.close(); return False

def init_database():
    os.makedirs(DATA_DIR, exist_ok=True)
    with WALManager(DB_PATH) as conn:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, display_order INTEGER NOT NULL UNIQUE)")
            conn.execute("CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, command TEXT NOT NULL, display_order INTEGER NOT NULL UNIQUE)")
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (key TEXT PRIMARY KEY, name TEXT NOT NULL, command_template TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS multi_runs (id TEXT PRIMARY KEY, repo TEXT NOT NULL, prompt TEXT NOT NULL, agents TEXT NOT NULL, status TEXT DEFAULT 'running', created_at TEXT DEFAULT CURRENT_TIMESTAMP, review_rank TEXT)")
            if conn.execute("SELECT COUNT(*) FROM config").fetchone()[0] == 0:
                default_prompt = get_prompt('default') or ''
                for k, v in [('claude_prompt', default_prompt), ('codex_prompt', default_prompt), ('gemini_prompt', default_prompt), ('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees")), ('multi_default', 'l:3')]: conn.execute("INSERT INTO config VALUES (?, ?)", (k, v))
            conn.execute("INSERT OR IGNORE INTO config VALUES ('multi_default', 'l:3')")
            conn.execute("INSERT OR IGNORE INTO config VALUES ('claude_prefix', 'Ultrathink. ')")
            if conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
                conn.execute("INSERT INTO projects (path, display_order) VALUES (?, ?)", (os.path.expanduser("~/projects/aio"), 0))
            if conn.execute("SELECT COUNT(*) FROM apps").fetchone()[0] == 0:
                conn.execute("INSERT INTO apps (name, command, display_order) VALUES (?, ?, ?)", ("testRepo", f"cd {os.path.expanduser('~/projects/testRepoPrivate')} && $SHELL", 0))
            if conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0:
                for key, name, cmd in [('h', 'htop', 'htop'), ('t', 'top', 'top'), ('g', 'gemini', 'gemini --yolo'), ('gp', 'gemini-p', 'gemini --yolo "{GEMINI_PROMPT}"'), ('c', 'codex', 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox'), ('cp', 'codex-p', 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox "{CODEX_PROMPT}"'), ('l', 'claude', 'claude --dangerously-skip-permissions'), ('lp', 'claude-p', 'claude --dangerously-skip-permissions "{CLAUDE_PROMPT}"'), ('o', 'claude', 'claude --dangerously-skip-permissions')]:
                    conn.execute("INSERT INTO sessions VALUES (?, ?, ?)", (key, name, cmd))
            conn.execute("INSERT OR IGNORE INTO sessions VALUES ('o', 'claude', 'claude --dangerously-skip-permissions')")

def load_config():
    with WALManager(DB_PATH) as conn: return dict(conn.execute("SELECT key, value FROM config").fetchall())

def get_prompt(name, show_location=False):
    prompt_file = PROMPTS_DIR / f'{name}.txt'
    if prompt_file.exists():
        if show_location: print(f"📝 Prompt: {prompt_file}")
        return prompt_file.read_text().strip()
    return None

def load_projects():
    with WALManager(DB_PATH) as conn: return [row[0] for row in conn.execute("SELECT path FROM projects ORDER BY display_order").fetchall()]

def add_project(path):
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path): return False, f"Path does not exist: {path}"
    if not os.path.isdir(path): return False, f"Path is not a directory: {path}"
    with WALManager(DB_PATH) as conn:
        with conn:
            if conn.execute("SELECT COUNT(*) FROM projects WHERE path = ?", (path,)).fetchone()[0] > 0: return False, f"Project already exists: {path}"
            max_order = conn.execute("SELECT MAX(display_order) FROM projects").fetchone()[0]
            conn.execute("INSERT INTO projects (path, display_order) VALUES (?, ?)", (path, (max_order + 1) if max_order is not None else 0))
    return True, f"Added project: {path}"

def remove_project(index):
    with WALManager(DB_PATH) as conn:
        with conn:
            projects = conn.execute("SELECT id, path FROM projects ORDER BY display_order").fetchall()
            if index < 0 or index >= len(projects): return False, f"Invalid project index: {index}"
            project_id, project_path = projects[index]
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            for i, pid in enumerate([row[0] for row in conn.execute("SELECT id FROM projects ORDER BY display_order").fetchall()]):
                conn.execute("UPDATE projects SET display_order = ? WHERE id = ?", (i, pid))
    return True, f"Removed project: {project_path}"

def load_apps():
    with WALManager(DB_PATH) as conn: return [(row[0], row[1]) for row in conn.execute("SELECT name, command FROM apps ORDER BY display_order").fetchall()]

def add_app(name, command):
    if not name or not command: return False, "Name and command are required"
    with WALManager(DB_PATH) as conn:
        with conn:
            if conn.execute("SELECT COUNT(*) FROM apps WHERE name = ?", (name,)).fetchone()[0] > 0: return False, f"App already exists: {name}"
            max_order = conn.execute("SELECT MAX(display_order) FROM apps").fetchone()[0]
            conn.execute("INSERT INTO apps (name, command, display_order) VALUES (?, ?, ?)", (name, command, (max_order + 1) if max_order is not None else 0))
    return True, f"Added app: {name}"

def remove_app(index):
    with WALManager(DB_PATH) as conn:
        with conn:
            apps = conn.execute("SELECT id, name FROM apps ORDER BY display_order").fetchall()
            if index < 0 or index >= len(apps): return False, f"Invalid app index: {index}"
            app_id, app_name = apps[index]
            conn.execute("DELETE FROM apps WHERE id = ?", (app_id,))
            for i, aid in enumerate([row[0] for row in conn.execute("SELECT id FROM apps ORDER BY display_order").fetchall()]):
                conn.execute("UPDATE apps SET display_order = ? WHERE id = ?", (i, aid))
    return True, f"Removed app: {app_name}"

def load_sessions(config):
    with WALManager(DB_PATH) as conn: sessions_data = conn.execute("SELECT key, name, command_template FROM sessions").fetchall()
    default_prompt, sessions = get_prompt('default'), {}
    for key, name, cmd_template in sessions_data:
        is_single_p = key in ['cp', 'lp', 'gp']
        claude_prompt = config.get('claude_prompt', default_prompt).replace('\n', '\\n').replace('"', '\\"')
        codex_prompt = config.get('codex_prompt', default_prompt).replace('\n', '\\n').replace('"', '\\"')
        gemini_prompt = config.get('gemini_prompt', default_prompt).replace('\n', '\\n').replace('"', '\\"')
        if is_single_p:
            cmd = cmd_template.replace(' "{CLAUDE_PROMPT}"', '').replace(' "{CODEX_PROMPT}"', '').replace(' "{GEMINI_PROMPT}"', '')
        else:
            cmd = cmd_template.format(CLAUDE_PROMPT=claude_prompt, CODEX_PROMPT=codex_prompt, GEMINI_PROMPT=gemini_prompt)
        sessions[key] = (name, cmd)
    return sessions

# Stage 3 initialization
_stage3_initialized = False
config, DEFAULT_PROMPT, CLAUDE_PROMPT, CODEX_PROMPT, GEMINI_PROMPT = {}, None, None, None, None
CLAUDE_PREFIX, WORK_DIR, WORKTREES_DIR = 'Ultrathink. ', None, None
PROJECTS, APPS, sessions = [], [], {}

def _init_stage3(skip_deps_check=False):
    global _stage3_initialized, config, DEFAULT_PROMPT, CLAUDE_PROMPT, CODEX_PROMPT, GEMINI_PROMPT, CLAUDE_PREFIX, WORK_DIR, WORKTREES_DIR, PROJECTS, APPS, sessions
    if _stage3_initialized: return
    _stage3_initialized = True
    init_database()
    config = load_config()
    DEFAULT_PROMPT = get_prompt('default')
    CLAUDE_PROMPT, CODEX_PROMPT, GEMINI_PROMPT = config.get('claude_prompt', DEFAULT_PROMPT), config.get('codex_prompt', DEFAULT_PROMPT), config.get('gemini_prompt', DEFAULT_PROMPT)
    CLAUDE_PREFIX = config.get('claude_prefix', 'Ultrathink. ')
    try: WORK_DIR = os.getcwd()
    except FileNotFoundError: WORK_DIR = os.path.expanduser("~"); os.chdir(WORK_DIR); print(f"⚠ Current directory was invalid, changed to: {WORK_DIR}")
    WORKTREES_DIR = config.get('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees"))
    PROJECTS, APPS, sessions = load_projects(), load_apps(), load_sessions(config)
    ensure_deps(skip_check=skip_deps_check)
    try: check_for_updates_warning()
    except: pass

# Tmux configuration
def _get_clipboard_cmd():
    if os.environ.get('TERMUX_VERSION'): return 'termux-clipboard-set'
    if sys.platform == 'darwin': return 'pbcopy'
    for cmd in ['wl-copy', 'xclip -selection clipboard -i', 'xsel --clipboard --input']:
        if shutil.which(cmd.split()[0]): return cmd
    return None

def _write_tmux_conf():
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
set -s set-clipboard on
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
    if clip_cmd: conf += f'set -s copy-command "{clip_cmd}"\nbind -T copy-mode MouseDragEnd1Pane send -X copy-pipe-and-cancel\nbind -T copy-mode-vi MouseDragEnd1Pane send -X copy-pipe-and-cancel\n'
    if sm.version >= '3.6': conf += 'set -g pane-scrollbars on\nset -g pane-scrollbars-position right\n'
    with open(_TMUX_CONF, 'w') as f: f.write(conf)
    return True

def ensure_tmux_options():
    _write_tmux_conf()
    if sp.run(['tmux', 'info'], stdout=sp.DEVNULL, stderr=sp.DEVNULL).returncode != 0: return
    r = sp.run(['tmux', 'source-file', _TMUX_CONF], capture_output=True, text=True)
    if r.returncode != 0: print(f"⚠ tmux config error: {r.stderr.strip()}"); return
    sp.run(['tmux', 'refresh-client', '-S'], capture_output=True)

def create_tmux_session(session_name, work_dir, cmd, env=None, capture_output=True):
    result = sm.new_session(session_name, work_dir, cmd or '', env)
    ensure_tmux_options()
    if cmd and any(a in cmd for a in ['codex', 'claude', 'gemini']):
        sp.run(['tmux', 'split-window', '-v', '-t', session_name, '-c', work_dir, 'bash -c "ls;exec bash"'], capture_output=True)
        sp.run(['tmux', 'select-pane', '-t', session_name, '-U'], capture_output=True)
        sp.run(['tmux', 'pipe-pane', '-t', session_name, '-o', f"bash -c 'while read -t5 _; do tmux set -t {shlex.quote(session_name)} set-titles-string \"🟢 #S:#W\" 2>/dev/null || break; done'"], capture_output=True)
    return result

# Terminal and session helpers
def detect_terminal():
    for term in ['ptyxis', 'gnome-terminal', 'alacritty']:
        if shutil.which(term): return term
    return None

def launch_in_new_window(session_name, terminal=None):
    terminal = terminal or detect_terminal()
    if not terminal: print("✗ No supported terminal found"); return False
    attach_cmd = sm.attach(session_name)
    cmd = {'ptyxis': ['ptyxis', '--'], 'gnome-terminal': ['gnome-terminal', '--'], 'alacritty': ['alacritty', '-e']}.get(terminal, []) + attach_cmd
    try: sp.Popen(cmd); print(f"✓ Launched {terminal} for session: {session_name}"); return True
    except Exception as e: print(f"✗ Failed to launch terminal: {e}"); return False

def launch_terminal_in_dir(directory, terminal=None):
    terminal = terminal or detect_terminal()
    if not terminal: print("✗ No supported terminal found"); return False
    directory = os.path.abspath(os.path.expanduser(directory))
    if not os.path.exists(directory): print(f"✗ Directory does not exist: {directory}"); return False
    cmd = {'ptyxis': ['ptyxis', '--working-directory', directory], 'gnome-terminal': ['gnome-terminal', f'--working-directory={directory}'], 'alacritty': ['alacritty', '--working-directory', directory]}.get(terminal, [])
    try: sp.Popen(cmd); print(f"✓ Launched {terminal} in: {directory}"); return True
    except Exception as e: print(f"✗ Failed to launch terminal: {e}"); return False

def is_pane_receiving_output(session_name, threshold=10):
    r = sp.run(['tmux', 'display-message', '-p', '-t', session_name, '#{window_activity}'], capture_output=True, text=True)
    if r.returncode != 0: return False
    try: return int(time.time()) - int(r.stdout.strip()) < threshold
    except: return False

# Worktrees (compact - 12 lines)
def wt_list():
    items = sorted([d for d in os.listdir(WORKTREES_DIR) if os.path.isdir(os.path.join(WORKTREES_DIR, d))]) if os.path.exists(WORKTREES_DIR) else []
    print("Worktrees:") if items else print("No worktrees"); [print(f"  {i}. {d}") for i, d in enumerate(items)]; return items
def wt_find(p):
    items = sorted([d for d in os.listdir(WORKTREES_DIR) if os.path.isdir(os.path.join(WORKTREES_DIR, d))]) if os.path.exists(WORKTREES_DIR) else []
    return os.path.join(WORKTREES_DIR, items[int(p)]) if p.isdigit() and 0 <= int(p) < len(items) else next((os.path.join(WORKTREES_DIR, i) for i in items if p in i), None)
def wt_create(proj, name):
    os.makedirs(WORKTREES_DIR, exist_ok=True); wt = os.path.join(WORKTREES_DIR, f"{os.path.basename(proj)}-{name}")
    r = _git(proj, 'worktree', 'add', '-b', f"wt-{os.path.basename(proj)}-{name}", wt, 'HEAD')
    return (print(f"✓ {wt}"), wt)[1] if r.returncode == 0 else (print(f"✗ {r.stderr.strip()}"), None)[1]
def wt_remove(path, confirm=True):
    if not os.path.exists(path): print(f"✗ Not found: {path}"); return False
    proj = next((p for p in PROJECTS if os.path.basename(path).startswith(os.path.basename(p) + '-')), PROJECTS[0] if PROJECTS else None)
    if confirm and input(f"Remove {os.path.basename(path)}? (y/n): ").lower() not in ['y', 'yes']: return False
    _git(proj, 'worktree', 'remove', '--force', path); _git(proj, 'branch', '-D', f"wt-{os.path.basename(path)}")
    os.path.exists(path) and shutil.rmtree(path); print(f"✓ Removed {os.path.basename(path)}"); return True

def wait_for_agent_ready(session_name, timeout=5):
    ready_patterns = [re.compile(p, re.MULTILINE) for p in [r'›.*\n\n\s+\d+%\s+context left', r'>\s+Type your message', r'gemini-2\.5-pro.*\(\d+%\)', r'──+\s*\n>\s+\w+']]
    start, last = time.time(), ""
    while (time.time() - start) < timeout:
        r = sp.run(['tmux', 'capture-pane', '-t', session_name, '-p'], capture_output=True, text=True)
        if r.returncode != 0: return False
        if r.stdout != last:
            for p in ready_patterns:
                if p.search(r.stdout): return True
            last = r.stdout
        time.sleep(0.2)
    return True

def get_agent_prefix(agent, work_dir=None):
    prefix = config.get('claude_prefix', 'Ultrathink. ') if 'claude' in agent else ''
    agents = Path(work_dir or os.getcwd()) / 'AGENTS.md'
    return prefix + (agents.read_text().strip() + ' ' if agents.exists() else '')

def enhance_prompt(prompt, agent='', work_dir=None):
    prefix = get_agent_prefix(agent, work_dir)
    return (prefix if prefix and not prompt.startswith(prefix.strip()) else '') + prompt

def send_prompt_to_session(session_name, prompt, wait_for_completion=False, timeout=None, wait_for_ready=True, send_enter=True):
    if not sm.has_session(session_name): print(f"✗ Session {session_name} not found"); return False
    if wait_for_ready:
        print(f"⏳ Waiting for agent to be ready...", end='', flush=True)
        print(" ✓" if wait_for_agent_ready(session_name) else " (timeout, sending anyway)")
    prompt = enhance_prompt(prompt, session_name)
    sm.send_keys(session_name, prompt)
    if send_enter:
        time.sleep(0.1); sm.send_keys(session_name, '\n'); print(f"✓ Sent prompt to session '{session_name}'")
    else: print(f"✓ Inserted prompt into session '{session_name}' (ready to edit/run)")
    if wait_for_completion:
        print("⏳ Waiting for completion...", end='', flush=True)
        start, last_active, idle_threshold = time.time(), time.time(), 3
        while True:
            if timeout and (time.time() - start) > timeout: print(f"\n⚠ Timeout ({timeout}s) reached"); return True
            if is_pane_receiving_output(session_name, threshold=2): last_active = time.time(); print(".", end='', flush=True)
            elif (time.time() - last_active) > idle_threshold: print("\n✓ Completed (activity stopped)"); return True
            time.sleep(0.5)
    return True

def get_or_create_directory_session(session_key, target_dir):
    if session_key not in sessions: return None
    base_name, cmd_template = sessions[session_key]
    r = sm.list_sessions()
    if r.returncode == 0:
        for session in [s for s in r.stdout.strip().split('\n') if s]:
            if not (session == base_name or session.startswith(base_name + '-')): continue
            path_r = sp.run(['tmux', 'display-message', '-p', '-t', session, '#{pane_current_path}'], capture_output=True, text=True)
            if path_r.returncode == 0 and path_r.stdout.strip() == target_dir: return session
    dir_name, session_name = os.path.basename(target_dir), f"{base_name}-{os.path.basename(target_dir)}"
    attempt, final = 0, session_name
    while sm.has_session(final): attempt += 1; final = f"{session_name}-{attempt}"
    return final

# Ghost sessions
def _ghost_spawn(dir_path, sessions_map):
    if not os.path.isdir(dir_path) or not shutil.which('tmux'): return
    state_file = os.path.join(DATA_DIR, 'ghost_state.json')
    try:
        with open(state_file) as f: state = json.load(f)
        if time.time() - state.get('time', 0) > _GHOST_TIMEOUT:
            for k in ['c', 'l', 'g']: sp.run(['tmux', 'kill-session', '-t', f'{_GHOST_PREFIX}{k}'], capture_output=True)
    except: pass
    for key in ['c', 'l', 'g']:
        ghost = f'{_GHOST_PREFIX}{key}'
        if sm.has_session(ghost):
            r = sp.run(['tmux', 'display-message', '-p', '-t', ghost, '#{pane_current_path}'], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip() == dir_path: continue
            sp.run(['tmux', 'kill-session', '-t', ghost], capture_output=True)
        _, cmd = sessions_map.get(key, (None, None))
        if cmd:
            create_tmux_session(ghost, dir_path, cmd)
            prefix = get_agent_prefix({'c': 'codex', 'l': 'claude', 'g': 'gemini'}[key], dir_path)
            if prefix: sp.Popen([sys.executable, __file__, 'send', ghost, prefix, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    try:
        with open(state_file, 'w') as f: json.dump({'dir': dir_path, 'time': time.time()}, f)
    except: pass

def _ghost_claim(agent_key, target_dir):
    ghost = f'{_GHOST_PREFIX}{_GHOST_MAP.get(agent_key, agent_key)}'
    if not sm.has_session(ghost): return None
    r = sp.run(['tmux', 'display-message', '-p', '-t', ghost, '#{pane_current_path}'], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != target_dir:
        sp.run(['tmux', 'kill-session', '-t', ghost], capture_output=True); return None
    return ghost

# Rclone/gdrive
def _get_rclone(): return shutil.which('rclone') or next((p for p in ['/usr/bin/rclone', os.path.expanduser('~/.local/bin/rclone')] if os.path.isfile(p)), None)

def _rclone_configured():
    r = sp.run([_get_rclone(), 'listremotes'], capture_output=True, text=True) if _get_rclone() else None
    return r and r.returncode == 0 and f'{RCLONE_REMOTE}:' in r.stdout

def _rclone_account():
    if not (rc := _get_rclone()): return None
    try:
        token = json.loads(json.loads(sp.run([rc, 'config', 'dump'], capture_output=True, text=True).stdout).get(RCLONE_REMOTE, {}).get('token', '{}')).get('access_token')
        if not token: return None
        import urllib.request
        u = json.loads(urllib.request.urlopen(urllib.request.Request('https://www.googleapis.com/drive/v3/about?fields=user', headers={'Authorization': f'Bearer {token}'}), timeout=5).read()).get('user', {})
        return f"{u.get('displayName', '')} <{u.get('emailAddress', 'unknown')}>"
    except: return None

_RCLONE_ERR_FILE = Path(DATA_DIR) / '.rclone_err'

def _rclone_sync_data(wait=False):
    if not (rc := _get_rclone()) or not _rclone_configured(): return False, None
    def _sync():
        r = sp.run([rc, 'sync', str(Path(SCRIPT_DIR) / 'data'), f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}', '-q'], capture_output=True, text=True)
        _RCLONE_ERR_FILE.write_text(r.stderr) if r.returncode != 0 else _RCLONE_ERR_FILE.unlink(missing_ok=True); return r.returncode == 0
    return (True, _sync()) if wait else (__import__('threading').Thread(target=_sync, daemon=True).start(), (True, None))[1]

def _rclone_pull_notes():
    if not (rc := _get_rclone()) or not _rclone_configured(): return False
    sp.run([rc, 'copy', f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}/notebook', str(Path(SCRIPT_DIR) / 'data' / 'notebook'), '-u', '-q'], capture_output=True); return True

# Jobs listing
def list_jobs(running_only=False):
    r = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True)
    jobs_by_path = {}
    if r.returncode == 0:
        for session in [s for s in r.stdout.strip().split('\n') if s]:
            path_r = sp.run(['tmux', 'display-message', '-p', '-t', session, '#{pane_current_path}'], capture_output=True, text=True)
            if path_r.returncode == 0:
                sess_path = path_r.stdout.strip()
                jobs_by_path.setdefault(sess_path, []).append(session)
    if os.path.exists(WORKTREES_DIR):
        for item in os.listdir(WORKTREES_DIR):
            wp = os.path.join(WORKTREES_DIR, item)
            if os.path.isdir(wp) and wp not in jobs_by_path: jobs_by_path[wp] = []
    if not jobs_by_path: print("No jobs found"); return
    jobs = []
    for jp in list(jobs_by_path.keys()):
        if not os.path.exists(jp):
            for s in jobs_by_path[jp]: sp.run(['tmux', 'kill-session', '-t', s], capture_output=True)
            continue
        is_wt = jp.startswith(WORKTREES_DIR)
        is_active = any(is_pane_receiving_output(s) for s in jobs_by_path[jp]) if jobs_by_path[jp] else False
        if running_only and not is_active: continue
        m = re.search(r'-(\d{8})-(\d{6})-', os.path.basename(jp))
        ct = datetime.strptime(f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S") if m else None
        td = (datetime.now() - ct).total_seconds() if ct else 0
        ct_disp = f"{int(td/60)}m ago" if td < 3600 else f"{int(td/3600)}h ago" if td < 86400 else f"{int(td/86400)}d ago" if ct else ""
        jobs.append({'path': jp, 'name': os.path.basename(jp), 'sessions': jobs_by_path[jp], 'is_wt': is_wt, 'is_active': is_active, 'ct': ct, 'ct_disp': ct_disp})
    jobs.sort(key=lambda x: x['ct'] if x['ct'] else datetime.min)
    print("Jobs:\n")
    for j in jobs:
        status = "🏃 RUNNING" if j['is_active'] else "📋 REVIEW"
        wt = ' [worktree]' if j['is_wt'] else ''
        ct = f" ({j['ct_disp']})" if j['ct_disp'] else ''
        print(f"  {status}  {j['name']}{wt}{ct}")
        print(f"           aio {j['path'].replace(os.path.expanduser('~'), '~')}")
        for s in j['sessions']: print(f"           tmux attach -t {s}")
        print()

def parse_agent_specs_and_prompt(argv, start_idx):
    agent_specs, prompt_parts, parsing_agents = [], [], True
    for arg_part in argv[start_idx:]:
        if arg_part in ['--seq', '--sequential']: continue
        if parsing_agents and ':' in arg_part and len(arg_part) <= 4:
            parts = arg_part.split(':')
            if len(parts) == 2 and parts[0] in ['c', 'l', 'g'] and parts[1].isdigit():
                agent_specs.append((parts[0], int(parts[1]))); continue
        parsing_agents = False
        prompt_parts.append(arg_part)
    return (agent_specs, CODEX_PROMPT, True) if not prompt_parts else (agent_specs, ' '.join(prompt_parts), False)

def format_app_command(app_cmd, max_length=60):
    display_cmd = app_cmd.replace(os.path.expanduser('~'), '~')
    return display_cmd[:max_length-3] + "..." if len(display_cmd) > max_length else display_cmd

def list_all_items(show_help=True, update_cache=True):
    projects, apps = load_projects(), load_apps(); Path(os.path.join(DATA_DIR, 'projects.txt')).write_text('\n'.join(projects) + '\n')
    lines = ([f"📁 PROJECTS:"] + [f"  {i}. {'✓' if os.path.exists(p) else '✗'} {p}" for i, p in enumerate(projects)] if projects else []) + ([f"\n⚡ COMMANDS:"] + [f"  {len(projects)+i}. {n} → {format_app_command(c)}" for i, (n, c) in enumerate(apps)] if apps else [])
    if lines: print('\n'.join(lines).replace('\n\n', '\n')); update_cache and Path(os.path.join(DATA_DIR, 'help_cache.txt')).write_text(HELP_SHORT + '\n' + '\n'.join(lines).replace('\n\n', '\n') + '\n')
    if show_help and (projects or apps): print(f"\n💡 aio add [path|name cmd]  aio remove <#|name>")
    return projects, apps

def auto_backup_check():
    if not hasattr(os, 'fork'): return
    ts_file = os.path.join(DATA_DIR, ".backup_timestamp")
    if os.path.exists(ts_file) and time.time() - os.path.getmtime(ts_file) < 600: return
    if os.fork() == 0:
        bp = os.path.join(DATA_DIR, f"aio_auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        with sqlite3.connect(DB_PATH) as src, sqlite3.connect(bp) as dst: src.backup(dst)
        Path(ts_file).touch(); os._exit(0)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
arg = sys.argv[1] if len(sys.argv) > 1 else None
_STAGE2_MAX_MS = 50
_stage2_ms = int((time.time() - _START) * 1000)
if _stage2_ms > _STAGE2_MAX_MS: print(f"⚠️  PERFORMANCE ERROR: Stage 2 took {_stage2_ms}ms (max {_STAGE2_MAX_MS}ms)"); sys.exit(1)

_init_stage3(skip_deps_check=(arg in ('install', 'deps')))
show_update_warning()
work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None
new_window = '--new-window' in sys.argv or '-w' in sys.argv
with_terminal = '--with-terminal' in sys.argv or '-t' in sys.argv
if new_window: sys.argv = [a for a in sys.argv if a not in ['--new-window', '-w']]; arg = sys.argv[1] if len(sys.argv) > 1 else None; work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None
if with_terminal: sys.argv = [a for a in sys.argv if a not in ['--with-terminal', '-t']]; arg = sys.argv[1] if len(sys.argv) > 1 else None; work_dir_arg = sys.argv[2] if len(sys.argv) > 2 else None; new_window = True

is_directory_only = new_window and arg and not arg.startswith('+') and not arg.endswith('--') and not arg.startswith('w') and arg not in sessions
if is_directory_only: work_dir_arg, arg = arg, None

is_work_dir_a_prompt = False
_cmd_keywords = {'add', 'remove', 'rm', 'cmd', 'command', 'commands', 'app', 'apps', 'prompt', 'a', 'all', 'review', 'w'}
if work_dir_arg and work_dir_arg.isdigit() and arg not in _cmd_keywords:
    idx = int(work_dir_arg)
    if 0 <= idx < len(PROJECTS): work_dir = PROJECTS[idx]
    elif 0 <= idx - len(PROJECTS) < len(APPS):
        app_name, app_command = APPS[idx - len(PROJECTS)]
        print(f"▶️  Running: {app_name}\n   Command: {app_command}")
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash'), '-c', app_command])
    else: work_dir = WORK_DIR
elif work_dir_arg and os.path.isdir(os.path.expanduser(work_dir_arg)): work_dir = work_dir_arg
elif work_dir_arg: is_work_dir_a_prompt = True; work_dir = WORK_DIR
else: work_dir = WORK_DIR

# Project number shortcut
if arg and arg.isdigit() and not work_dir_arg:
    idx = int(arg)
    if 0 <= idx < len(PROJECTS):
        print(f"📂 Opening project {idx}: {PROJECTS[idx]}")
        sp.Popen([sys.executable, __file__, '_ghost', PROJECTS[idx]], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        os.chdir(PROJECTS[idx]); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    elif 0 <= idx - len(PROJECTS) < len(APPS):
        app_name, app_command = APPS[idx - len(PROJECTS)]
        print(f"▶️  Running: {app_name}\n   Command: {format_app_command(app_command)}")
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash'), '-c', app_command])
    else: print(f"✗ Invalid index: {idx}"); sys.exit(1)

# Worktree commands (compact - 5 lines)
if arg and arg.startswith('w') and arg != 'watch' and not os.path.isfile(arg):
    if arg == 'w': wt_list(); sys.exit(0)
    wp = wt_find(arg[1:].rstrip('-'))
    if arg.endswith('-'): wt_remove(wp, confirm='--yes' not in sys.argv and '-y' not in sys.argv) if wp else print(f"✗ Not found"); sys.exit(0)
    if wp: os.chdir(wp); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    print(f"✗ Not found: {arg[1:]}"); sys.exit(1)

if new_window and not arg: launch_terminal_in_dir(work_dir); sys.exit(0)
if arg == '_ghost':
    if len(sys.argv) > 2: _init_stage3(); _ghost_spawn(sys.argv[2], sessions)
    sys.exit(0)

# Command dispatch table
HELP_SHORT = f"""aio - AI agent session manager
QUICK START:
  aio c               Start agent (c=codex l/o=claude g=gemini)
  aio dash            Dashboard with jobs monitor
  aio fix             AI finds/fixes issues
  aio bug "task"      Fix a bug
  aio feat "task"     Add a feature
ALL (multi-agent):
  aio a c:3               Launch 3 codex in parallel worktrees
  aio a c:3 "task"        Launch with task
  aio a c:2 l:1           Mixed: 2 codex + 1 claude
GIT:
  aio push src/ msg   Push folder with message
  aio pull            Sync with server
MANAGEMENT:
  aio jobs            Show active jobs
  aio attach          Reconnect to session
  aio kill            Kill all tmux sessions
  aio cleanup         Delete all worktrees
Run 'aio help' for all commands"""

HELP_FULL = f"""aio - AI agent session manager
SESSIONS: c=codex l/o=claude g=gemini h=htop t=top
  aio <key> [#|dir]      Start session (# = project index)
  aio <key>-- [#]        New worktree  |  aio +<key>  New timestamped
  aio cp/lp/gp           Insert prompt (edit first)
  aio <key> "prompt"     Send custom prompt  |  -w new window  -t +terminal
WORKFLOWS: aio fix|bug|feat|auto|del [agent] ["task"]
WORKTREES: aio w  list | w<#>  open | w<#>-  delete | w<#>--  push+delete
ADD/REMOVE: aio add [path|name "cmd"]  aio remove <#|name>
MONITOR: jobs [-r] | review | cleanup | ls | attach | kill
GIT: push [file] [msg] | pull [-y] | revert [N] | setup <url>
CONFIG: install | deps | update | font [+|-|N] | config [key] [val]
DB: ~/.local/share/aios/aio.db  Worktrees: {WORKTREES_DIR}"""

def cmd_help(): print(HELP_SHORT); list_all_items(show_help=False)
def cmd_help_full(): print(HELP_FULL); list_all_items(show_help=False)
def cmd_update(): manual_update()
def cmd_jobs(): list_jobs(running_only='--running' in sys.argv or '-r' in sys.argv)

def cmd_kill():
    if input("Kill all tmux sessions? (y/n): ").lower() in ['y', 'yes']:
        if 'TMUX' in os.environ: sp.run(['tmux', 'detach-client'])
        sp.run(['pkill', '-9', 'tmux']); print("✓ Killed all tmux")

def cmd_attach():
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

def cmd_cleanup():
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

def cmd_config():
    key, val = work_dir_arg, ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else None
    if not key: [print(f"  {k}: {v[:50]}{'...' if len(v)>50 else ''}") for k, v in sorted(config.items())]
    elif val:
        with WALManager(DB_PATH) as c: c.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (key, val)); c.commit()
        print(f"✓ {key}={val}")
    else: print(f"{key}: {config.get(key, '(not set)')}")

def cmd_ls():
    r = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True)
    if r.returncode != 0: print("No tmux sessions found"); sys.exit(0)
    sessions_list = [s for s in r.stdout.strip().split('\n') if s]
    if not sessions_list: print("No tmux sessions found"); sys.exit(0)
    print("Tmux Sessions:\n")
    for session in sessions_list:
        path_r = sp.run(['tmux', 'display-message', '-p', '-t', session, '#{pane_current_path}'], capture_output=True, text=True)
        print(f"  {session}: {path_r.stdout.strip() if path_r.returncode == 0 else ''}")

def cmd_diff():
    sp.run(['git', 'fetch', 'origin'], capture_output=True); cwd = os.getcwd()
    b = sp.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True).stdout.strip()
    target, diff = 'origin/main' if b.startswith('wt-') else f'origin/{b}', sp.run(['git', 'diff', 'origin/main' if b.startswith('wt-') else f'origin/{b}'], capture_output=True, text=True).stdout
    untracked = sp.run(['git', 'ls-files', '--others', '--exclude-standard'], capture_output=True, text=True).stdout.strip()
    print(f"📂 {cwd}\n🌿 {b} → {target}")
    if not diff and not untracked: print("No changes"); sys.exit(0)
    G, R, X, f = '\033[48;2;26;84;42m', '\033[48;2;117;34;27m', '\033[0m', ''
    for L in diff.split('\n'):
        if L.startswith('diff --git'): f = L.split(' b/')[-1]
        elif L.startswith('@@'): m = re.search(r'\+(\d+)', L); print(f"\n{f} line {m.group(1)}:" if m else "")
        elif L.startswith('+') and not L.startswith('+++'): print(f"  {G}+ {L[1:]}{X}")
        elif L.startswith('-') and not L.startswith('---'): print(f"  {R}- {L[1:]}{X}")
    if untracked: print(f"\nUntracked:\n" + '\n'.join(f"  {G}+ {u}{X}" for u in untracked.split('\n')))
    stat = sp.run(['git', 'diff', target, '--shortstat'], capture_output=True, text=True).stdout.strip()
    ins, dels = (int(re.search(r'(\d+) insertion', stat).group(1)) if 'insertion' in stat else 0), (int(re.search(r'(\d+) deletion', stat).group(1)) if 'deletion' in stat else 0)
    stat and print(f"\n{stat} | Net: {'+' if ins-dels >= 0 else ''}{ins-dels} lines")

def cmd_send():
    work_dir_arg or _die("Usage: aio send <session> <prompt> [--wait] [--no-enter]")
    prompt = ' '.join(a for a in sys.argv[3:] if a not in ('--wait', '--no-enter'))
    prompt or _die("No prompt provided")
    send_prompt_to_session(work_dir_arg, prompt, wait_for_completion='--wait' in sys.argv, timeout=60, send_enter='--no-enter' not in sys.argv) or sys.exit(1)

def cmd_watch():
    work_dir_arg or _die("Usage: aio watch <session> [duration]")
    dur = int(sys.argv[3]) if len(sys.argv) > 3 else None
    print(f"👁 Watching '{work_dir_arg}'" + (f" for {dur}s" if dur else " (once)"))
    patterns = {re.compile(p): r for p, r in [(r'Are you sure\?', 'y'), (r'Continue\?', 'yes'), (r'\[y/N\]', 'y'), (r'\[Y/n\]', 'y')]}
    last, start = "", time.time()
    while True:
        if dur and (time.time() - start) > dur: break
        r = sp.run(['tmux', 'capture-pane', '-t', work_dir_arg, '-p'], capture_output=True, text=True)
        if r.returncode != 0: print(f"✗ Session {work_dir_arg} not found"); sys.exit(1)
        if r.stdout != last:
            for p, resp in patterns.items():
                if p.search(r.stdout): sp.run(['tmux', 'send-keys', '-t', work_dir_arg, resp, 'Enter']); print(f"✓ Auto-responded"); break
            last = r.stdout
        time.sleep(0.1)

def cmd_push():
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
        wt_name = os.path.basename(cwd)
        proj = next((p for p in PROJECTS if wt_name.startswith(os.path.basename(p) + '-')), None) or _die(f"✗ Could not find project for {wt_name}")
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
        cur, main = _git(cwd, 'branch', '--show-current').stdout.strip(), _git_main(cwd)
        _git(cwd, 'add', target) if target else _git(cwd, 'add', '-A')
        r = _git(cwd, 'commit', '-m', msg)
        if r.returncode == 0: print(f"✓ Committed: {msg}")
        elif 'nothing to commit' in r.stdout: print("ℹ No changes"); sys.exit(0)
        else: _die(f"✗ Commit failed: {r.stderr.strip() or r.stdout.strip()}")
        if cur != main:
            _git(cwd, 'checkout', main).returncode == 0 or _die(f"✗ Checkout failed")
            _git(cwd, 'merge', cur, '--no-edit', '-X', 'theirs').returncode == 0 or _die("✗ Merge failed")
            print(f"✓ Merged {cur} → {main}")
        _git(cwd, 'fetch', 'origin', env=env)
        _git_push(cwd, main, env) or sys.exit(1)

def cmd_pull():
    cwd = os.getcwd(); _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("✗ Not a git repo")
    env = get_noninteractive_git_env(); _git(cwd, 'fetch', 'origin', env=env)
    ref = 'origin/main' if _git(cwd, 'rev-parse', '--verify', 'origin/main').returncode == 0 else 'origin/master'
    info = _git(cwd, 'log', '-1', '--format=%h %s', ref).stdout.strip()
    print(f"⚠ DELETE local changes → {info}")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").strip().lower() in ['y', 'yes']) or _die("✗ Cancelled")
    _git(cwd, 'reset', '--hard', ref); _git(cwd, 'clean', '-f', '-d'); print(f"✓ Synced: {info}")

def cmd_revert():
    cwd = os.getcwd(); _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("✗ Not a git repo")
    n = int(work_dir_arg) if work_dir_arg and work_dir_arg.isdigit() else 1
    r = _git(cwd, 'revert', 'HEAD', '--no-edit') if n == 1 else _git(cwd, 'revert', f'HEAD~{n}..HEAD', '--no-edit')
    print(f"✓ Reverted {n} commit(s)") if r.returncode == 0 else _die(f"✗ Revert failed: {r.stderr.strip()}")

def cmd_setup():
    cwd = os.getcwd()
    if not os.path.isdir(os.path.join(cwd, '.git')): _git(cwd, 'init', '-b', 'main'); print("✓ Initialized")
    if _git(cwd, 'rev-parse', 'HEAD').returncode != 0:
        _git(cwd, 'add', '-A')
        if _git(cwd, 'diff', '--cached', '--quiet').returncode == 0: Path(os.path.join(cwd, '.gitignore')).touch(); _git(cwd, 'add', '.gitignore')
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
            user = sp.run(['gh', 'api', 'user', '-q', '.login'], capture_output=True, text=True).stdout.strip()
            url = r.stdout.strip() or f"https://github.com/{user}/{name}.git"
            print("✓ Created/connected repo")
    if not url and not has_remote: url = input("Enter remote URL (Enter to skip): ").strip()
    if url:
        _git(cwd, 'remote', 'set-url' if has_remote else 'remote', 'add', 'origin', url) if has_remote else _git(cwd, 'remote', 'add', 'origin', url)
        print(f"✓ Remote: {url}")
    env = get_noninteractive_git_env()
    r = _git(cwd, 'push', '-u', 'origin', 'main', env=env)
    print("✓ Pushed" if r.returncode == 0 else "ℹ Push skipped")

def cmd_install():
    bin_dir, script_path = os.path.expanduser("~/.local/bin"), os.path.realpath(__file__)
    os.makedirs(bin_dir, exist_ok=True)
    aio_link = os.path.join(bin_dir, "aio")
    if os.path.islink(aio_link): os.remove(aio_link)
    elif os.path.exists(aio_link): _die(f"✗ {aio_link} exists but is not a symlink")
    os.symlink(script_path, aio_link); print(f"✓ Symlink: {aio_link}")
    shell = os.environ.get('SHELL', '/bin/bash')
    rc = os.path.expanduser('~/.config/fish/config.fish' if 'fish' in shell else ('~/.zshrc' if 'zsh' in shell else '~/.bashrc'))
    func = '''# aio instant startup
aio() { local d="${1/#~/$HOME}"; [[ -d "$d" ]] && { cd "$d"; ls; return; }; command python3 ~/.local/bin/aio "$@"; }''' if 'fish' not in shell else '''function aio; command python3 ~/.local/bin/aio $argv; end'''
    if 'aio' not in (Path(rc).read_text() if os.path.exists(rc) else ''):
        try:
            if input(f"Add to {rc}? [Y/n]: ").strip().lower() != 'n': Path(rc).open('a').write(func + '\n'); print(f"✓ Added")
        except: pass
    def _ok(p):
        try: return bool(shutil.which(p)) if p in 'tmux wl-copy npm codex claude gemini'.split() else (__import__(p), True)[1]
        except: return False
    _a, _n = {'pexpect': 'python3-pexpect', 'prompt_toolkit': 'python3-prompt-toolkit', 'tmux': 'tmux', 'wl-copy': 'wl-clipboard'}, {'codex': '@openai/codex', 'claude': '@anthropic-ai/claude-code', 'gemini': '@google/gemini-cli'}
    ok, am, nm = [p for p in list(_a)+list(_n)+['npm'] if _ok(p)], ' '.join(_a[p] for p in _a if not _ok(p)), ' '.join(_n[p] for p in _n if not _ok(p))
    ok and print(f"✓ Have: {', '.join(ok)}")
    cmds = [f"sudo apt install {am}" for _ in [1] if am and shutil.which('apt-get')] + [f"sudo npm install -g {nm}" for _ in [1] if nm]
    cmds and print(f"\n📦 Run:\n  {' && '.join(cmds)}")

def cmd_deps():
    import platform, urllib.request, tarfile, lzma
    bin_dir = os.path.expanduser('~/.local/bin'); os.makedirs(bin_dir, exist_ok=True)
    def _i(p, a=None):
        try: __import__(p); print(f"✓ {p}"); return True
        except: pass
        if a and shutil.which('apt-get') and sp.run(['sudo','apt-get','install','-y',a], capture_output=True).returncode == 0: print(f"✓ {p}"); return True
        for brk in [[], ['--break-system-packages']]:
            if sp.run([sys.executable,'-m','pip','install','--user']+brk+[p], capture_output=True).returncode == 0: print(f"✓ {p}"); return True
        print(f"✗ {p}"); return False
    print("📦 Installing deps...\n")
    _i('pexpect', 'python3-pexpect'); _i('prompt_toolkit', 'python3-prompt-toolkit')
    if not shutil.which('tmux'):
        cmds = [['brew', 'install', 'tmux']] if sys.platform == 'darwin' else ([['sudo', 'apt-get', 'install', '-y', 'tmux']] if shutil.which('apt-get') else [['pkg', 'install', '-y', 'tmux']])
        any(sp.run(c, capture_output=True).returncode == 0 for c in cmds) and print("✓ tmux") or print("✗ tmux")
    else: print("✓ tmux")
    node_dir, node_bin = os.path.expanduser('~/.local/node'), os.path.expanduser('~/.local/node/bin')
    npm_path = os.path.join(node_bin, 'npm')
    if not shutil.which('npm') and not os.path.exists(npm_path):
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
        if not shutil.which(cmd):
            try: sp.run([npm_cmd, 'install', '-g', pkg], check=True, capture_output=True); print(f"✓ {cmd}")
            except: print(f"✗ {cmd}")
        else: print(f"✓ {cmd}")
    print("\n✅ Done!")

def cmd_prompt():
    name = work_dir_arg or 'feat'
    prompt_file = PROMPTS_DIR / f'{name}.txt'
    if not prompt_file.exists(): print(f"📝 Prompts dir: {PROMPTS_DIR}\nAvailable: {', '.join(p.stem for p in PROMPTS_DIR.glob('*.txt'))}"); sys.exit(1)
    print(f"📝 Editing: {prompt_file}")
    current = prompt_file.read_text().strip()
    new_val = input_box(current, f"Edit '{name}' (Ctrl+D to save, Ctrl+C to cancel)")
    if new_val is None: print("Cancelled")
    elif new_val.strip() != current: prompt_file.write_text(new_val.strip()); print(f"✓ Saved")
    else: print("No changes")

def cmd_gdrive():
    rc = _get_rclone()
    if not rc and work_dir_arg == 'login':
        import platform; bd, arch = os.path.expanduser('~/.local/bin'), 'amd64' if platform.machine() in ('x86_64', 'AMD64') else 'arm64'
        print(f"Installing rclone..."); os.makedirs(bd, exist_ok=True)
        if sp.run(f'curl -sL https://downloads.rclone.org/rclone-current-linux-{arch}.zip -o /tmp/rclone.zip && unzip -qjo /tmp/rclone.zip "*/rclone" -d {bd} && chmod +x {bd}/rclone', shell=True).returncode == 0:
            rc = f'{bd}/rclone'; print(f"✓ Installed")
        else: _die("rclone install failed")
    if work_dir_arg == 'login':
        rc or _die("rclone not found")
        if _rclone_configured() and not _confirm("Already logged in. Switch account?"): sys.exit(0)
        sp.run([rc, 'config', 'create', RCLONE_REMOTE, 'drive'])
        if _rclone_configured(): _ok(f"Logged in as {_rclone_account() or 'unknown'}"); _rclone_sync_data(wait=True)
        else: _err("Login failed - try again")
    elif work_dir_arg == 'logout':
        if _rclone_configured(): sp.run([rc, 'config', 'delete', RCLONE_REMOTE]); _ok("Logged out")
        else: print("Not logged in")
    elif _rclone_configured(): _ok(f"Logged in: {_rclone_account() or RCLONE_REMOTE}")
    else: _err("Not logged in. Run: aio gdrive login")

def cmd_note():
    import threading
    NOTEBOOK_DIR = Path(SCRIPT_DIR) / 'data' / 'notebook'; NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    def _slug(s): return re.sub(r'[^\w\-]', '', s.split('\n')[0][:40].lower().replace(' ', '-'))[:30] or 'note'
    def _preview(p): return p.read_text().split('\n')[0][:60]
    raw = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    notes = sorted(NOTEBOOK_DIR.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
    threading.Thread(target=_rclone_pull_notes, daemon=True).start()
    if not raw or raw == 'ls':
        if not notes: print("No notes. Create: aio note <content>"); sys.exit(0)
        for i, n in enumerate(notes): print(f"{i}. {_preview(n)}")
        if raw == 'ls': sys.exit(0)
        ch = input("View #: ").strip()
        if ch.isdigit() and int(ch) < len(notes): print(f"\n{notes[int(ch)].read_text()}")
    elif raw.isdigit():
        if int(raw) < len(notes): print(notes[int(raw)].read_text())
        else: print(f"No note #{raw}")
    else:
        content = raw if raw.strip() else input_box('', 'Note')
        if content:
            nf = NOTEBOOK_DIR / f"{_slug(content)}-{datetime.now().strftime('%m%d%H%M')}.md"
            nf.write_text(content); print(f"✓ {_preview(nf)}")
            started, _ = _rclone_sync_data()
            print("☁ Syncing..." if started else "💡 Run 'aio gdrive login' for cloud backup")

def cmd_add():
    args = [a for a in sys.argv[2:] if a != '--global']
    is_global = '--global' in sys.argv[2:]
    if len(args) >= 2 and not os.path.isdir(os.path.expanduser(args[0])):
        interpreters = ['python', 'python3', 'node', 'npm', 'ruby', 'perl', 'java', 'go', 'sh', 'bash', 'npx']
        if args[0] in interpreters:
            cmd_val = ' '.join(args); print(f"Command: {cmd_val}")
            cmd_name = input("Name for this command: ").strip()
            if not cmd_name: print("✗ Cancelled"); sys.exit(1)
        else: cmd_name, cmd_val = args[0], ' '.join(args[1:])
        cwd, home = os.getcwd(), os.path.expanduser('~')
        if not is_global and cwd != home and not cmd_val.startswith('cd '): cmd_val = f"cd {cwd.replace(home, '~')} && {cmd_val}"
        ok, msg = add_app(cmd_name, cmd_val); print(f"{'✓' if ok else '✗'} {msg}")
        if ok: auto_backup_check(); list_all_items()
        sys.exit(0 if ok else 1)
    path = os.path.abspath(os.path.expanduser(args[0])) if args else os.getcwd()
    ok, msg = add_project(path); print(f"{'✓' if ok else '✗'} {msg}")
    if ok: auto_backup_check(); list_all_items()
    sys.exit(0 if ok else 1)

def cmd_remove():
    if not work_dir_arg: print("Usage: aio remove <#|name>\n"); list_all_items(); sys.exit(0)
    projects, apps = load_projects(), load_apps()
    if work_dir_arg.isdigit():
        idx = int(work_dir_arg)
        if idx < len(projects): ok, msg = remove_project(idx)
        elif idx < len(projects) + len(apps): ok, msg = remove_app(idx - len(projects))
        else: print(f"✗ Invalid index: {idx}"); list_all_items(); sys.exit(1)
    else:
        app_idx = next((i for i, (n, _) in enumerate(apps) if n.lower() == work_dir_arg.lower()), None)
        if app_idx is None: print(f"✗ Not found: {work_dir_arg}"); list_all_items(); sys.exit(1)
        ok, msg = remove_app(app_idx)
    print(f"{'✓' if ok else '✗'} {msg}")
    if ok: auto_backup_check(); list_all_items()
    sys.exit(0 if ok else 1)

def cmd_dash():
    sn = 'dash'
    if not sm.has_session(sn):
        sp.run(['tmux', 'new-session', '-d', '-s', sn, '-c', work_dir])
        sp.run(['tmux', 'split-window', '-h', '-t', sn, '-c', work_dir, 'bash -c "aio jobs; exec bash"'])
    os.execvp('tmux', ['tmux', 'attach', '-t', sn] if 'TMUX' not in os.environ else ['tmux', 'switch-client', '-t', sn])

def cmd_fix_bug_feat_auto_del():
    args = sys.argv[2:]
    agent = 'l'
    if args and args[0] in ('c', 'l', 'g'): agent, args = args[0], args[1:]
    prompt_template = get_prompt(arg, show_location=True) or '{task}'
    if arg in ('fix', 'auto', 'del'): prompt, task = prompt_template, 'autonomous'
    else:
        task = ' '.join(args) if args else input(f"{arg}: ")
        prompt = prompt_template.format(task=task)
    agent_name, cmd = sessions[agent]
    session_name = f"{arg}-{agent}-{datetime.now().strftime('%H%M%S')}"
    print(f"📝 {arg.upper()} [{agent_name}]: {task[:50]}{'...' if len(task) > 50 else ''}")
    prompt = enhance_prompt(prompt, agent_name)
    create_tmux_session(session_name, os.getcwd(), f"{cmd} {shlex.quote(prompt)}")
    launch_in_new_window(session_name) if 'TMUX' in os.environ else os.execvp(sm.attach(session_name)[0], sm.attach(session_name))

def cmd_multi():
    if work_dir_arg == 'set':
        ns = ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else ''
        if not ns: print(f"Current: {load_config().get('multi_default', 'c:3')}"); sys.exit(0)
        if not parse_agent_specs_and_prompt([''] + ns.split(), 1)[0]: _die(f"Invalid: {ns}")
        with WALManager(DB_PATH) as c: c.execute("INSERT OR REPLACE INTO config VALUES ('multi_default', ?)", (ns,)); c.commit()
        print(f"✓ Default: {ns}"); sys.exit(0)
    project_path, start = (PROJECTS[int(work_dir_arg)], 3) if work_dir_arg and work_dir_arg.isdigit() and int(work_dir_arg) < len(PROJECTS) else (os.getcwd(), 2)
    agent_specs, _, _ = parse_agent_specs_and_prompt(sys.argv, start)
    if not agent_specs:
        ds = load_config().get('multi_default', 'l:3'); agent_specs, _, _ = parse_agent_specs_and_prompt([''] + ds.split(), 1)
        print(f"Using: {ds}")
    total, repo_name, run_id = sum(c for _, c in agent_specs), os.path.basename(project_path), datetime.now().strftime('%Y%m%d-%H%M%S')
    session_name, run_dir = f"{repo_name}-{run_id}", os.path.join(WORKTREES_DIR, repo_name, run_id)
    candidates_dir = os.path.join(run_dir, "candidates"); os.makedirs(candidates_dir, exist_ok=True)
    with open(os.path.join(run_dir, "run.json"), "w") as f: json.dump({"agents": [f"{k}:{c}" for k, c in agent_specs], "created": run_id, "repo": project_path}, f)
    with WALManager(DB_PATH) as c: c.execute("INSERT OR REPLACE INTO multi_runs VALUES (?, ?, '', ?, 'running', CURRENT_TIMESTAMP, NULL)", (run_id, project_path, json.dumps([f"{k}:{c}" for k, c in agent_specs]))); c.commit()
    print(f"🚀 {total} agents in {repo_name}/{run_id}..."); env, launched, agent_num, first = get_noninteractive_git_env(), [], {}, True
    for ak, cnt in agent_specs:
        bn, bc = sessions.get(ak, (None, None))
        if not bn: continue
        for i in range(cnt):
            agent_num[bn] = agent_num.get(bn, 0) + 1; wn, an = f"{bn}-{agent_num[bn]}", f"{ak}{i}"
            wt = os.path.join(candidates_dir, an); sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', f'wt-{repo_name}-{run_id}-{an}', wt], capture_output=True, env=env)
            if not os.path.exists(wt): continue
            sp.run(['tmux', 'new-session', '-d', '-s', session_name, '-n', wn, '-c', wt, bc] if first else ['tmux', 'new-window', '-t', session_name, '-n', wn, '-c', wt, bc], env=env); first = False
            sp.run(['tmux', 'split-window', '-h', '-t', f'{session_name}:{wn}', '-c', wt], env=env)
            launched.append((wn, bn, wt)); print(f"✓ {wn}")
    if not launched: print("✗ No agents created"); sys.exit(1)
    wins = ' '.join(w for w, _, _ in launched)
    ctrl = f'''echo -e "\\n  🎮 AIO ALL - {session_name}\\n\\n  Agents: {wins}\\n\\n  Type below to send to ALL agents (Enter to send)\\n  Ctrl+C: exit broadcast | Ctrl+N: switch window\\n"
s="{session_name}"; wins=({wins}); while read -ep "all> " cmd; do [ -n "$cmd" ] && for w in "${{wins[@]}}"; do tmux send-keys -t "$s:$w" "$cmd" Enter; done; done'''
    sp.run(['tmux', 'new-window', '-t', session_name, '-n', '🎮', '-c', candidates_dir], env=env)
    sp.run(['tmux', 'send-keys', '-t', f'{session_name}:🎮', ctrl, 'Enter'])
    sp.run(['tmux', 'split-window', '-v', '-t', f'{session_name}:🎮', '-c', candidates_dir], env=env)
    sp.run(['tmux', 'select-window', '-t', f'{session_name}:🎮'], capture_output=True)
    ensure_tmux_options()
    print(f"\n✓ Session '{session_name}': {len(launched)} agents + 🎮 control\n   Type in 🎮 window to broadcast to all agents")
    if "TMUX" in os.environ: print(f"   tmux switch-client -t {session_name}")
    else: os.execvp('tmux', ['tmux', 'attach', '-t', session_name])

def cmd_e():
    if 'TMUX' in os.environ: os.execvp('nvim', ['nvim', '.'])
    else:
        create_tmux_session('edit', os.getcwd(), 'nvim .')
        os.execvp('tmux', ['tmux', 'attach', '-t', 'edit'])

def cmd_x(): sp.run(['tmux', 'kill-server']); print("✓ All sessions killed")
def cmd_p(): list_all_items(show_help=False)

def cmd_worktree_plus():
    key = arg[:-2]
    if key not in sessions: print(f"✗ Unknown session key: {key}"); return
    proj = PROJECTS[int(work_dir_arg)] if work_dir_arg and work_dir_arg.isdigit() and int(work_dir_arg) < len(PROJECTS) else work_dir
    base_name, cmd = sessions[key]
    wp = wt_create(proj, f"{base_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    if not wp: return
    sn = os.path.basename(wp); create_tmux_session(sn, wp, cmd, env=get_noninteractive_git_env(), capture_output=False)
    prefix = get_agent_prefix(base_name, wp)
    if prefix: sp.Popen([sys.executable, __file__, 'send', sn, prefix, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    if new_window: launch_in_new_window(sn)
    elif "TMUX" in os.environ: print(f"✓ Session: {sn}")
    else: os.execvp(sm.attach(sn)[0], sm.attach(sn))

def cmd_dir_or_file():
    if os.path.isdir(os.path.expanduser(arg)):
        d = os.path.expanduser('~' + arg) if arg.startswith('/projects/') else os.path.expanduser(arg)
        print(f"📂 {d}", flush=True); sp.run(['ls', d])
    elif os.path.isfile(arg):
        ext = os.path.splitext(arg)[1].lower()
        if ext == '.py': os.execvp(sys.executable, [sys.executable, arg] + sys.argv[2:])
        elif ext in ('.html', '.htm'): __import__('webbrowser').open('file://' + os.path.abspath(arg))
        elif ext == '.md': os.execvp(os.environ.get('EDITOR', 'nvim'), [os.environ.get('EDITOR', 'nvim'), arg])

def cmd_session():
    # Ghost claiming - pre-warmed session for instant startup
    if arg in _GHOST_MAP and not work_dir_arg:
        ghost = _ghost_claim(arg, work_dir)
        if ghost:
            agent_name = sessions[arg][0] if arg in sessions else arg
            sn = f"{agent_name}-{os.path.basename(work_dir)}"
            sp.run(['tmux', 'rename-session', '-t', ghost, sn], capture_output=True)
            print(f"⚡ Ghost claimed: {sn}")
            if 'TMUX' in os.environ: os.execvp('tmux', ['tmux', 'switch-client', '-t', sn])
            else: os.execvp(sm.attach(sn)[0], sm.attach(sn))
        # Ghost not available - fall through to create new session
    # Inside tmux - create pane
    if 'TMUX' in os.environ and arg in sessions and len(arg) == 1:
        agent_name, cmd = sessions[arg]
        sp.run(['tmux', 'split-window', '-bv', '-c', work_dir, cmd])
        prefix = get_agent_prefix(agent_name, work_dir)
        if prefix: time.sleep(0.5); sp.run(['tmux', 'send-keys', '-t', '!', '-l', prefix])
        sys.exit(0)
    session_name = get_or_create_directory_session(arg, work_dir)
    if session_name is None:
        name, cmd = sessions.get(arg, (arg, None))
        env = get_noninteractive_git_env()
        create_tmux_session(name, work_dir, cmd or arg, env=env)
        session_name = name
    else:
        if not sm.has_session(session_name):
            _, cmd = sessions[arg]
            env = get_noninteractive_git_env()
            create_tmux_session(session_name, work_dir, cmd, env=env)
    is_single_p = arg.endswith('p') and not arg.endswith('pp') and len(arg) == 2 and arg in sessions
    prompt_start_idx = 2 if is_work_dir_a_prompt else (3 if work_dir_arg else 2)
    prompt_parts = [sys.argv[i] for i in range(prompt_start_idx, len(sys.argv)) if sys.argv[i] not in ['-w', '--new-window', '--yes', '-y', '-t', '--with-terminal']]
    if prompt_parts:
        prompt = ' '.join(prompt_parts)
        print(f"📤 Prompt queued")
        cmd = [sys.executable, __file__, 'send', session_name, prompt]
        if is_single_p: cmd.append('--no-enter')
        sp.Popen(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif is_single_p:
        prompt_map = {'cp': CODEX_PROMPT, 'lp': CLAUDE_PROMPT, 'gp': GEMINI_PROMPT}
        if prompt_map.get(arg): sp.Popen([sys.executable, __file__, 'send', session_name, prompt_map[arg], '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif arg in sessions:
        prefix = get_agent_prefix(sessions[arg][0], work_dir)
        if prefix: sp.Popen([sys.executable, __file__, 'send', session_name, prefix, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    if new_window: launch_in_new_window(session_name); with_terminal and launch_terminal_in_dir(work_dir)
    elif "TMUX" in os.environ or not sys.stdout.isatty(): print(f"✓ Session: {session_name}")
    else: os.execvp(sm.attach(session_name)[0], sm.attach(session_name))

# Command dispatch
COMMANDS = {
    None: cmd_help, '': cmd_help, 'help': cmd_help_full, '--help': cmd_help_full, '-h': cmd_help_full,
    'update': cmd_update, 'jobs': cmd_jobs, 'kill': cmd_kill, 'killall': cmd_kill, 'attach': cmd_attach,
    'cleanup': cmd_cleanup, 'config': cmd_config, 'ls': cmd_ls, 'diff': cmd_diff, 'send': cmd_send,
    'watch': cmd_watch, 'push': cmd_push, 'pull': cmd_pull, 'revert': cmd_revert, 'setup': cmd_setup,
    'install': cmd_install, 'deps': cmd_deps, 'prompt': cmd_prompt, 'gdrive': cmd_gdrive, 'note': cmd_note,
    'add': cmd_add, 'remove': cmd_remove, 'rm': cmd_remove, 'dash': cmd_dash, 'a': cmd_multi, 'all': cmd_multi,
    'e': cmd_e, 'x': cmd_x, 'p': cmd_p, 'dir': lambda: (print(f"📂 {os.getcwd()}"), sp.run(['ls'])),
    'fix': cmd_fix_bug_feat_auto_del, 'bug': cmd_fix_bug_feat_auto_del, 'feat': cmd_fix_bug_feat_auto_del,
    'auto': cmd_fix_bug_feat_auto_del, 'del': cmd_fix_bug_feat_auto_del,
}

if arg in COMMANDS: COMMANDS[arg]()
elif arg and arg.endswith('++') and not arg.startswith('w'): cmd_worktree_plus()
elif arg and (os.path.isdir(os.path.expanduser(arg)) or os.path.isfile(arg) or (arg.startswith('/projects/') and os.path.isdir(os.path.expanduser('~' + arg)))): cmd_dir_or_file()
elif arg in sessions or (arg and len(arg) <= 3): cmd_session()
else: cmd_session()
