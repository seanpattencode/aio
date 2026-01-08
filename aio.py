#!/usr/bin/env python3
# aio - AI agent session manager (compact version)
import sys, os
if len(sys.argv) > 2 and sys.argv[1] == 'note' and sys.argv[2] not in ('ls',) and not sys.argv[2].isdigit() and os.path.exists(ND := os.path.expanduser("~/.local/share/aios/notebook")):
    import subprocess as sp, re; from datetime import datetime; raw = ' '.join(sys.argv[2:]); slug = re.sub(r'[^\w\-]', '', raw.split('\n')[0][:40].lower().replace(' ', '-'))[:30] or 'note'; gc = f"{ND}/.git/config"; gh = os.path.exists(gc) and 'remote' in open(gc).read(); gh and sp.run(f'git -C "{ND}" pull --rebase -q', shell=True, capture_output=True, timeout=5); open(f"{ND}/{slug}-{datetime.now().strftime('%m%d%H%M')}.md", 'w').write(raw); sp.Popen(f'git -C "{ND}" add -A && git -C "{ND}" commit -m "add {slug}" && git -C "{ND}" push', shell=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL); print("✓ github" if gh else "✓ local"); sys.exit(0)
import subprocess as sp, json, sqlite3, shlex, shutil, time, atexit, re
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
def _err(msg): print(f"x {msg}")
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
    if missing: print(f"! Missing: {', '.join(missing)}. Run: aio install"); sys.exit(1)

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
        except sp.TimeoutExpired: return (sp.run(['pkill', '-9', 'tmux']), False)[1] if input("! tmux hung. Kill? (y/n): ").lower() == 'y' else sys.exit(1)
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
_AGENT_DIRS = {'claude': Path.home()/'.claude', 'codex': Path.home()/'.codex', 'gemini': Path.home()/'.gemini'}
# Tmux config strategy: write aio config to ~/.aios/tmux.conf, append source-file to user's ~/.tmux.conf
# Never overwrite user config - only append source line if missing. User can customize their own file.
_AIO_TMUX_DIR = os.path.expanduser('~/.aios')
_AIO_TMUX_CONF = os.path.join(_AIO_TMUX_DIR, 'tmux.conf')
_USER_TMUX_CONF = os.path.expanduser('~/.tmux.conf')
_AIO_MARKER, _AIO_SOURCE_LINE = '# aio-managed-config', f'source-file ~/.aios/tmux.conf  # aio'

# Git helpers
def _git_main(path):
    r = _git(path, 'symbolic-ref', 'refs/remotes/origin/HEAD')
    return r.stdout.strip().replace('refs/remotes/origin/', '') if r.returncode == 0 else ('main' if _git(path, 'rev-parse', '--verify', 'main').returncode == 0 else 'master')

def _git_push(path, branch, env, force=False):
    r = _git(path, 'push', *(['--force'] if force else []), 'origin', branch, env=env)
    if r.returncode == 0: print(f"✓ Pushed to {branch}"); return True
    err = r.stderr.strip() or r.stdout.strip()
    if 'non-fast-forward' in err and input("! Force push? (y/n): ").lower() in ['y', 'yes']:
        _git(path, 'fetch', 'origin', env=env); return _git_push(path, branch, env, True)
    print(f"x Push failed: {err}"); return False

def get_noninteractive_git_env():
    env = os.environ.copy()
    env.pop('DISPLAY', None); env.pop('GPG_AGENT_INFO', None)
    env['GIT_TERMINAL_PROMPT'] = '0'
    return env

# Update checking
def _sg(*a, **k): return sp.run(['git', '-C', SCRIPT_DIR] + list(a), capture_output=True, text=True, **k)  # script git
def manual_update():
    if _sg('rev-parse', '--git-dir').returncode != 0: print("x Not in a git repository"); return False
    print("Checking..."); before = _sg('rev-parse', 'HEAD').stdout.strip()[:8]
    if not before or _sg('fetch').returncode != 0: return False
    if 'behind' not in _sg('status', '-uno').stdout: print(f"✓ Up to date ({before})"); return True
    print("Downloading..."); _sg('pull', '--ff-only')
    after = _sg('rev-parse', 'HEAD'); print(f"✓ {before} -> {after.stdout.strip()[:8]}" if after.returncode == 0 else "✓ Done"); return True

def check_for_updates_warning():
    ts = os.path.join(DATA_DIR, '.update_check')
    if os.path.exists(ts) and time.time() - os.path.getmtime(ts) < 1800: return
    if not hasattr(os, 'fork') or os.fork() != 0: return
    try: Path(ts).touch(); r = _sg('fetch', '--dry-run', timeout=5); r.returncode == 0 and r.stderr.strip() and Path(os.path.join(DATA_DIR, '.update_available')).touch()
    except: pass
    os._exit(0)

def show_update_warning():
    m = os.path.join(DATA_DIR, '.update_available')
    if os.path.exists(m):
        if 'behind' in _sg('status', '-uno').stdout: print("! Update available! Run 'aio update'")
        else: os.path.exists(m) and os.remove(m)

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
                conn.execute("INSERT INTO apps (name, command, display_order) VALUES (?, ?, ?)", ("aioUI", f"python3 {os.path.expanduser('~/.local/bin/aioUI.py')}", 0))
            if conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0:
                _cdx = 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox'
                _cld = 'claude --dangerously-skip-permissions'
                for k, n, c in [('h','htop','htop'),('t','top','top'),('g','gemini','gemini --yolo'),('gp','gemini-p','gemini --yolo "{GEMINI_PROMPT}"'),('c','codex',_cdx),('cp','codex-p',f'{_cdx} "{{CODEX_PROMPT}}"'),('l','claude',_cld),('lp','claude-p',f'{_cld} "{{CLAUDE_PROMPT}}"'),('o','claude',_cld),('a','aider','OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral')]:
                    conn.execute("INSERT INTO sessions VALUES (?, ?, ?)", (k, n, c))
            conn.execute("INSERT OR IGNORE INTO sessions VALUES ('o', 'claude', 'claude --dangerously-skip-permissions')")
            conn.execute("INSERT OR IGNORE INTO sessions VALUES ('a', 'aider', 'OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral')")

def load_config():
    with WALManager(DB_PATH) as conn: return dict(conn.execute("SELECT key, value FROM config").fetchall())

def get_prompt(name, show_location=False):
    prompt_file = PROMPTS_DIR / f'{name}.txt'
    if prompt_file.exists():
        if show_location: print(f"Prompt: {prompt_file}")
        return prompt_file.read_text().strip()
    return None

def load_projects():
    with WALManager(DB_PATH) as conn: return [row[0] for row in conn.execute("SELECT path FROM projects ORDER BY display_order").fetchall()]

def add_project(path):
    p = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(p): return False, f"Not a directory: {p}"
    with WALManager(DB_PATH) as c:
        if c.execute("SELECT 1 FROM projects WHERE path=?", (p,)).fetchone(): return False, f"Exists: {p}"
        m = c.execute("SELECT MAX(display_order) FROM projects").fetchone()[0]
        c.execute("INSERT INTO projects (path, display_order) VALUES (?, ?)", (p, 0 if m is None else m+1)); c.commit()
    return True, f"Added: {p}"

def remove_project(idx):
    with WALManager(DB_PATH) as c:
        rows = c.execute("SELECT id, path FROM projects ORDER BY display_order").fetchall()
        if idx < 0 or idx >= len(rows): return False, f"Invalid index: {idx}"
        c.execute("DELETE FROM projects WHERE id=?", (rows[idx][0],))
        for i, r in enumerate(c.execute("SELECT id FROM projects ORDER BY display_order")): c.execute("UPDATE projects SET display_order=? WHERE id=?", (i, r[0]))
        c.commit()
    return True, f"Removed: {rows[idx][1]}"

def load_apps():
    with WALManager(DB_PATH) as c: return [(r[0], r[1]) for r in c.execute("SELECT name, command FROM apps ORDER BY display_order")]

def add_app(name, cmd):
    if not name or not cmd: return False, "Name and command required"
    with WALManager(DB_PATH) as c:
        if c.execute("SELECT 1 FROM apps WHERE name=?", (name,)).fetchone(): return False, f"Exists: {name}"
        m = c.execute("SELECT MAX(display_order) FROM apps").fetchone()[0]
        c.execute("INSERT INTO apps (name, command, display_order) VALUES (?, ?, ?)", (name, cmd, 0 if m is None else m+1)); c.commit()
    return True, f"Added: {name}"

def remove_app(idx):
    with WALManager(DB_PATH) as c:
        rows = c.execute("SELECT id, name FROM apps ORDER BY display_order").fetchall()
        if idx < 0 or idx >= len(rows): return False, f"Invalid index: {idx}"
        c.execute("DELETE FROM apps WHERE id=?", (rows[idx][0],))
        for i, r in enumerate(c.execute("SELECT id FROM apps ORDER BY display_order")): c.execute("UPDATE apps SET display_order=? WHERE id=?", (i, r[0]))
        c.commit()
    return True, f"Removed: {rows[idx][1]}"

def load_sessions(cfg):
    with WALManager(DB_PATH) as c: data = c.execute("SELECT key, name, command_template FROM sessions").fetchall()
    dp, s = get_prompt('default'), {}
    esc = lambda p: cfg.get(p, dp).replace('\n', '\\n').replace('"', '\\"')
    for k, n, t in data:
        s[k] = (n, t.replace(' "{CLAUDE_PROMPT}"', '').replace(' "{CODEX_PROMPT}"', '').replace(' "{GEMINI_PROMPT}"', '') if k in ['cp','lp','gp'] else t.format(CLAUDE_PROMPT=esc('claude_prompt'), CODEX_PROMPT=esc('codex_prompt'), GEMINI_PROMPT=esc('gemini_prompt')))
    return s

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
    except FileNotFoundError: WORK_DIR = os.path.expanduser("~"); os.chdir(WORK_DIR); print(f"! Current directory was invalid, changed to: {WORK_DIR}")
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
    # Write aio config to ~/.aios/tmux.conf, append source-file to user's ~/.tmux.conf (never overwrite)
    line0 = '#[align=left][#S]#[align=centre]#{W:#[range=window|#{window_index}]#I:#W#{?window_active,*,}#[norange] }'
    sh_full = '#[range=user|sess]Ctrl+N:Win#[norange] #[range=user|new]Ctrl+T:New#[norange] #[range=user|close]Ctrl+W:Close#[norange] #[range=user|edit]Ctrl+E:Edit#[norange] #[range=user|kill]Ctrl+X:Kill#[norange] #[range=user|detach]Ctrl+Q:Quit#[norange]'
    sh_min = '#[range=user|sess]Sess#[norange] #[range=user|new]New#[norange] #[range=user|close]Close#[norange] #[range=user|edit]Edit#[norange] #[range=user|kill]Kill#[norange] #[range=user|detach]Quit#[norange]'
    line1 = '#{?#{e|<:#{client_width},70},' + sh_min + ',' + sh_full + '}'
    line2 = '#[align=left]#[range=user|esc]Esc#[norange]#[align=centre]#[range=user|kbd]Keyboard#[norange]'
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
    # Write aio config to ~/.aios/tmux.conf
    os.makedirs(_AIO_TMUX_DIR, exist_ok=True)
    with open(_AIO_TMUX_CONF, 'w') as f: f.write(conf)
    # Append source line to user's ~/.tmux.conf if not present (never overwrite existing content)
    user_conf = Path(_USER_TMUX_CONF).read_text() if os.path.exists(_USER_TMUX_CONF) else ''
    if _AIO_SOURCE_LINE not in user_conf and '~/.aios/tmux.conf' not in user_conf:
        with open(_USER_TMUX_CONF, 'a') as f: f.write(f'\n{_AIO_SOURCE_LINE}\n')
    return True

def ensure_tmux_options():
    if config.get('tmux_conf') != 'y' or not _write_tmux_conf(): return
    if sp.run(['tmux', 'info'], stdout=sp.DEVNULL, stderr=sp.DEVNULL).returncode != 0: return
    r = sp.run(['tmux', 'source-file', _AIO_TMUX_CONF], capture_output=True, text=True)
    if r.returncode != 0: print(f"! tmux config error: {r.stderr.strip()}"); return
    sp.run(['tmux', 'refresh-client', '-S'], capture_output=True)

def create_tmux_session(sn, wd, cmd, env=None, capture_output=True):
    is_ai = cmd and any(a in cmd for a in ['codex', 'claude', 'gemini', 'aider'])
    if is_ai: cmd = f'while :; do {cmd}; e=$?; [ $e -eq 0 ] && break; echo -e "\\n! Crashed (exit $e). [R]estart / [Q]uit: "; read -n1 k; [[ $k =~ [Rr] ]] || break; done'
    r = sm.new_session(sn, wd, cmd or '', env); ensure_tmux_options()
    if is_ai: sp.run(['tmux', 'split-window', '-v', '-t', sn, '-c', wd, 'sh -c "ls;exec $SHELL"'], capture_output=True); sp.run(['tmux', 'select-pane', '-t', sn, '-U'], capture_output=True)
    return r

# Terminal and session helpers
def detect_terminal(): return next((t for t in ['ptyxis', 'gnome-terminal', 'alacritty'] if shutil.which(t)), None)
_TERM_ATTACH = {'ptyxis': ['ptyxis', '--'], 'gnome-terminal': ['gnome-terminal', '--'], 'alacritty': ['alacritty', '-e']}

def launch_in_new_window(sn, term=None):
    term = term or detect_terminal()
    if not term: print("x No terminal"); return False
    try: sp.Popen(_TERM_ATTACH.get(term, []) + sm.attach(sn)); print(f"✓ Launched {term}: {sn}"); return True
    except Exception as e: print(f"x {e}"); return False

def launch_terminal_in_dir(d, term=None):
    term, d = term or detect_terminal(), os.path.abspath(os.path.expanduser(d))
    if not term: print("x No terminal"); return False
    if not os.path.exists(d): print(f"x Not found: {d}"); return False
    cmds = {'ptyxis': ['ptyxis', '--working-directory', d], 'gnome-terminal': ['gnome-terminal', f'--working-directory={d}'], 'alacritty': ['alacritty', '--working-directory', d]}
    try: sp.Popen(cmds.get(term, [])); print(f"✓ {term}: {d}"); return True
    except Exception as e: print(f"x {e}"); return False

def is_pane_receiving_output(session_name, threshold=10):
    r = sp.run(['tmux', 'display-message', '-p', '-t', session_name, '#{window_activity}'], capture_output=True, text=True)
    if r.returncode != 0: return False
    try: return int(time.time()) - int(r.stdout.strip()) < threshold
    except: return False

# Worktrees (compact)
def _wt_items(): return sorted([d for d in os.listdir(WORKTREES_DIR) if os.path.isdir(os.path.join(WORKTREES_DIR, d))]) if os.path.exists(WORKTREES_DIR) else []
def wt_list(): items = _wt_items(); print("Worktrees:" if items else "No worktrees"); [print(f"  {i}. {d}") for i, d in enumerate(items)]; return items
def wt_find(p): items = _wt_items(); return os.path.join(WORKTREES_DIR, items[int(p)]) if p.isdigit() and 0 <= int(p) < len(items) else next((os.path.join(WORKTREES_DIR, i) for i in items if p in i), None)
def wt_create(proj, name):
    os.makedirs(WORKTREES_DIR, exist_ok=True); wt = os.path.join(WORKTREES_DIR, f"{os.path.basename(proj)}-{name}")
    r = _git(proj, 'worktree', 'add', '-b', f"wt-{os.path.basename(proj)}-{name}", wt, 'HEAD')
    return (print(f"✓ {wt}"), wt)[1] if r.returncode == 0 else (print(f"x {r.stderr.strip()}"), None)[1]
def wt_remove(path, confirm=True):
    if not os.path.exists(path): print(f"x Not found: {path}"); return False
    proj = next((p for p in PROJECTS if os.path.basename(path).startswith(os.path.basename(p) + '-')), PROJECTS[0] if PROJECTS else None)
    if confirm and input(f"Remove {os.path.basename(path)}? (y/n): ").lower() not in ['y', 'yes']: return False
    _git(proj, 'worktree', 'remove', '--force', path); _git(proj, 'branch', '-D', f"wt-{os.path.basename(path)}")
    os.path.exists(path) and shutil.rmtree(path); print(f"✓ Removed {os.path.basename(path)}"); return True

def get_agent_prefix(agent, wd=None):
    pre = config.get('claude_prefix', 'Ultrathink. ') if 'claude' in agent else ''
    af = Path(wd or os.getcwd()) / 'AGENTS.md'
    return pre + (af.read_text().strip() + ' ' if af.exists() else '')

def send_prefix(sn, agent, wd):
    """Send prefix via background subprocess (survives execvp)."""
    pre = get_agent_prefix(agent, wd)
    if not pre: return
    # Detect ready: "context" (old) or "claude"/"opus"/"gemini"/"codex" (new) in output
    script = f'import time,subprocess as s\nfor _ in range(30):\n time.sleep(0.5);r=s.run(["tmux","capture-pane","-t","{sn}","-p","-S","-50"],capture_output=True,text=True);o=r.stdout.lower()\n if r.returncode!=0 or any(x in o for x in["context","claude","opus","gemini","codex"]):break\ns.run(["tmux","send-keys","-l","-t","{sn}",{repr(pre)}])'
    sp.Popen([sys.executable, '-c', script], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

def send_prompt_to_session(sn, prompt, wait_done=False, timeout=None, send_enter=True):
    if not sm.has_session(sn): print(f"x Session {sn} not found"); return False
    sm.send_keys(sn, prompt)
    if send_enter: time.sleep(0.1); sm.send_keys(sn, '\n'); print(f"✓ Sent to '{sn}'")
    else: print(f"✓ Inserted into '{sn}'")
    if wait_done:
        print("Waiting...", end='', flush=True); start, last = time.time(), time.time()
        while True:
            if timeout and (time.time() - start) > timeout: print(f"\n! Timeout"); return True
            if is_pane_receiving_output(sn, threshold=2): last = time.time(); print(".", end='', flush=True)
            elif (time.time() - last) > 3: print("\n+ Done"); return True
            time.sleep(0.5)
    return True

def get_or_create_directory_session(key, target_dir):
    if key not in sessions: return None
    bn, _ = sessions[key]; r = sm.list_sessions()
    if r.returncode == 0:
        for s in [x for x in r.stdout.strip().split('\n') if x]:
            if not (s == bn or s.startswith(bn + '-')): continue
            pr = sp.run(['tmux', 'display-message', '-p', '-t', s, '#{pane_dead}:#{pane_current_path}'], capture_output=True, text=True)
            if pr.returncode == 0 and pr.stdout.strip().startswith('0:') and pr.stdout.strip()[2:] == target_dir: return s
    sn, i = f"{bn}-{os.path.basename(target_dir)}", 0
    while sm.has_session(sn if i == 0 else f"{sn}-{i}"): i += 1
    return sn if i == 0 else f"{sn}-{i}"

# Ghost sessions
def _ghost_spawn(dp, sm_map):
    if not os.path.isdir(dp) or not shutil.which('tmux'): return
    sf = os.path.join(DATA_DIR, 'ghost_state.json')
    try:
        with open(sf) as f: st = json.load(f)
        if time.time() - st.get('time', 0) > _GHOST_TIMEOUT: [sp.run(['tmux', 'kill-session', '-t', f'{_GHOST_PREFIX}{k}'], capture_output=True) for k in 'clg']
    except: pass
    for k in 'clg':
        g = f'{_GHOST_PREFIX}{k}'
        if sm.has_session(g):
            r = sp.run(['tmux', 'display-message', '-p', '-t', g, '#{pane_current_path}'], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip() == dp: continue
            sp.run(['tmux', 'kill-session', '-t', g], capture_output=True)
        _, cmd = sm_map.get(k, (None, None))
        if cmd: create_tmux_session(g, dp, cmd); send_prefix(g, {'c': 'codex', 'l': 'claude', 'g': 'gemini'}[k], dp)
    try: Path(sf).write_text(json.dumps({'dir': dp, 'time': time.time()}))
    except: pass

def _ghost_claim(ak, td):
    g = f'{_GHOST_PREFIX}{_GHOST_MAP.get(ak, ak)}'
    if not sm.has_session(g): return None
    r = sp.run(['tmux', 'display-message', '-p', '-t', g, '#{pane_current_path}'], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != td: sp.run(['tmux', 'kill-session', '-t', g], capture_output=True); return None
    return g

# Jobs listing
def list_jobs(running_only=False):
    r = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True)
    jbp = {}  # jobs_by_path
    for s in (r.stdout.strip().split('\n') if r.returncode == 0 else []):
        if s and (pr := sp.run(['tmux', 'display-message', '-p', '-t', s, '#{pane_current_path}'], capture_output=True, text=True)).returncode == 0:
            jbp.setdefault(pr.stdout.strip(), []).append(s)
    for wp in [os.path.join(WORKTREES_DIR, d) for d in (os.listdir(WORKTREES_DIR) if os.path.exists(WORKTREES_DIR) else []) if os.path.isdir(os.path.join(WORKTREES_DIR, d))]:
        if wp not in jbp: jbp[wp] = []
    if not jbp: print("No jobs found"); return
    jobs = []
    for jp, ss in list(jbp.items()):
        if not os.path.exists(jp): [sp.run(['tmux', 'kill-session', '-t', s], capture_output=True) for s in ss]; continue
        active = any(is_pane_receiving_output(s) for s in ss) if ss else False
        if running_only and not active: continue
        m = re.search(r'-(\d{8})-(\d{6})-', os.path.basename(jp))
        ct = datetime.strptime(f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S") if m else None
        td = (datetime.now() - ct).total_seconds() if ct else 0
        ct_d = f"{int(td/60)}m ago" if td < 3600 else f"{int(td/3600)}h ago" if td < 86400 else f"{int(td/86400)}d ago" if ct else ""
        jobs.append({'p': jp, 'n': os.path.basename(jp), 's': ss, 'wt': jp.startswith(WORKTREES_DIR), 'a': active, 'ct': ct, 'ctd': ct_d})
    print("Jobs:\n")
    for j in sorted(jobs, key=lambda x: x['ct'] or datetime.min):
        ctd = f" ({j['ctd']})" if j['ctd'] else ''
        print(f"  {'RUNNING' if j['a'] else 'REVIEW'}  {j['n']}{' [worktree]' if j['wt'] else ''}{ctd}")
        print(f"           aio {j['p'].replace(os.path.expanduser('~'), '~')}")
        for s in j['s']: print(f"           tmux attach -t {s}")
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
    p, a = load_projects(), load_apps(); Path(os.path.join(DATA_DIR, 'projects.txt')).write_text('\n'.join(p) + '\n')
    out = ([f"PROJECTS:"] + [f"  {i}. {'+' if os.path.exists(x) else 'x'} {x}" for i, x in enumerate(p)] if p else [])
    out += ([f"COMMANDS:"] + [f"  {len(p)+i}. {n} -> {format_app_command(c)}" for i, (n, c) in enumerate(a)] if a else [])
    if out: txt = '\n'.join(out); print(txt); update_cache and Path(os.path.join(DATA_DIR, 'help_cache.txt')).write_text(HELP_SHORT + '\n' + txt + '\n')
    if show_help and (p or a): print(f"\nTip: aio add [path|name cmd]  aio remove <#|name>")
    return p, a

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
if _stage2_ms > _STAGE2_MAX_MS: print(f"! PERFORMANCE ERROR: Stage 2 took {_stage2_ms}ms (max {_STAGE2_MAX_MS}ms)"); sys.exit(1)
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
        print(f"> Running: {app_name}\n   Command: {app_command}")
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash'), '-c', app_command])
    else: work_dir = WORK_DIR
elif work_dir_arg and os.path.isdir(os.path.expanduser(work_dir_arg)): work_dir = work_dir_arg
elif work_dir_arg: is_work_dir_a_prompt = True; work_dir = WORK_DIR
else: work_dir = WORK_DIR

# Project number shortcut
if arg and arg.isdigit() and not work_dir_arg:
    idx = int(arg)
    if 0 <= idx < len(PROJECTS):
        print(f"Opening project {idx}: {PROJECTS[idx]}")
        sp.Popen([sys.executable, __file__, '_ghost', PROJECTS[idx]], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        os.chdir(PROJECTS[idx]); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    elif 0 <= idx - len(PROJECTS) < len(APPS):
        app_name, app_command = APPS[idx - len(PROJECTS)]
        print(f"> Running: {app_name}\n   Command: {format_app_command(app_command)}")
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash'), '-c', app_command])
    else: print(f"x Invalid index: {idx}"); sys.exit(1)

# Worktree commands (compact - 5 lines)
if arg and arg.startswith('w') and arg != 'watch' and not os.path.isfile(arg):
    if arg == 'w': wt_list(); sys.exit(0)
    wp = wt_find(arg[1:].rstrip('-'))
    if arg.endswith('-'): wt_remove(wp, confirm='--yes' not in sys.argv and '-y' not in sys.argv) if wp else print(f"x Not found"); sys.exit(0)
    if wp: os.chdir(wp); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    print(f"x Not found: {arg[1:]}"); sys.exit(1)

if new_window and not arg: launch_terminal_in_dir(work_dir); sys.exit(0)
if arg == '_ghost':
    if len(sys.argv) > 2: _init_stage3(); _ghost_spawn(sys.argv[2], sessions)
    sys.exit(0)

# Command dispatch table
HELP_SHORT = f"""aio - AI agent session manager
QUICK START:
  aio c               Start agent (c=codex l/o=claude g=gemini a=aider)
  aio dash            Dashboard with jobs monitor
  aio fix             AI finds/fixes issues
  aio bug "task"      Fix a bug
  aio feat "task"     Add a feature
ALL (multi-agent):
  aio all c:3             Launch 3 codex in parallel worktrees
  aio all c:3 "task"      Launch with task
  aio all c:2 l:1         Mixed: 2 codex + 1 claude
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
SESSIONS: c=codex l/o=claude g=gemini a=aider h=htop t=top
  aio <key> [#|dir]      Start session (# = project index)
  aio <key>-- [#]        New worktree  |  aio +<key>  New timestamped
  aio cp/lp/gp           Insert prompt (edit first)
  aio <key> "prompt"     Send custom prompt  |  -w new window  -t +terminal
WORKFLOWS: aio fix|bug|feat|auto|del [agent] ["task"]
WORKTREES: aio w  list | w<#>  open | w<#>-  delete | w<#>--  push+delete
ADD/REMOVE: aio add [path|name "cmd"]  aio remove <#|name>
MONITOR: jobs [-r] | review | cleanup | ls | attach | kill
GIT: push [file] [msg] | pull [-y] | revert [N]
CONFIG: install | deps | update | font [+|-|N] | config [key] [val]
DB: ~/.local/share/aios/aio.db  Worktrees: {WORKTREES_DIR}"""

def cmd_help(): print(HELP_SHORT); list_all_items(show_help=False)
def cmd_help_full(): print(HELP_FULL); list_all_items(show_help=False)
def cmd_update(): manual_update()
def cmd_jobs(): list_jobs(running_only='--running' in sys.argv or '-r' in sys.argv)

def cmd_kill():
    if input("Kill all tmux sessions? (y/n): ").lower() in ['y', 'yes']:
        print("✓ Killed all tmux"); sp.run(['tmux', 'kill-server'])

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
    wts = _wt_items()
    with WALManager(DB_PATH) as c: db_cnt = c.execute("SELECT COUNT(*) FROM multi_runs").fetchone()[0]
    if not wts and not db_cnt: print("Nothing to clean"); sys.exit(0)
    print(f"Will delete: {len(wts)} dirs, {db_cnt} db entries")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").lower() in ['y', 'yes']) or _die("x")
    for wt in wts:
        try: shutil.rmtree(os.path.join(WORKTREES_DIR, wt)); print(f"✓ {wt}")
        except: pass
    [_git(p, 'worktree', 'prune') for p in PROJECTS if os.path.exists(p)]
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
    print(f"{cwd}\n{b} -> {target}")
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
    print(f"Watching '{work_dir_arg}'" + (f" for {dur}s" if dur else " (once)"))
    patterns = {re.compile(p): r for p, r in [(r'Are you sure\?', 'y'), (r'Continue\?', 'yes'), (r'\[y/N\]', 'y'), (r'\[Y/n\]', 'y')]}
    last, start = "", time.time()
    while True:
        if dur and (time.time() - start) > dur: break
        r = sp.run(['tmux', 'capture-pane', '-t', work_dir_arg, '-p'], capture_output=True, text=True)
        if r.returncode != 0: print(f"x Session {work_dir_arg} not found"); sys.exit(1)
        if r.stdout != last:
            for p, resp in patterns.items():
                if p.search(r.stdout): sp.run(['tmux', 'send-keys', '-t', work_dir_arg, resp, 'Enter']); print(f"✓ Auto-responded"); break
            last = r.stdout
        time.sleep(0.1)

def cmd_push():
    cwd, skip = os.getcwd(), '--yes' in sys.argv or '-y' in sys.argv
    if _git(cwd, 'rev-parse', '--git-dir').returncode != 0:
        _git(cwd, 'init', '-b', 'main'); Path(os.path.join(cwd, '.gitignore')).touch(); _git(cwd, 'add', '-A'); _git(cwd, 'commit', '-m', 'Initial commit'); print("✓ Initialized")
        u = sys.argv[2] if len(sys.argv) > 2 and '://' in sys.argv[2] else ('' if skip else (input(f"Create '{os.path.basename(cwd)}' on GitHub? y=public p=private URL: ") if shutil.which('gh') else input("Remote URL: ")).strip())
        if u in 'y p yes private'.split() and sp.run(['gh', 'repo', 'create', os.path.basename(cwd), '--private' if 'p' in u else '--public', '--source', '.', '--push'], timeout=60).returncode == 0: print("✓ Pushed"); return
        if u and '://' in u: _git(cwd, 'remote', 'add', 'origin', u)
    ensure_git_config(); r = _git(cwd, 'rev-parse', '--git-dir'); is_wt = '.git/worktrees/' in r.stdout.strip() or cwd.startswith(WORKTREES_DIR)
    args = [a for a in sys.argv[2:] if a not in ['--yes', '-y'] and '://' not in a]
    target = args[0] if args and os.path.isfile(os.path.join(cwd, args[0])) else None
    if target: args = args[1:]
    msg = ' '.join(args) or (f"Update {target}" if target else f"Update {os.path.basename(cwd)}")
    env = get_noninteractive_git_env()
    if is_wt:
        wt_name = os.path.basename(cwd)
        proj = next((p for p in PROJECTS if wt_name.startswith(os.path.basename(p) + '-')), None) or _die(f"x Could not find project for {wt_name}")
        wt_branch = _git(cwd, 'branch', '--show-current').stdout.strip()
        print(f"Worktree: {wt_name} | Branch: {wt_branch} | Msg: {msg}")
        to_main = skip or input("Push to: 1=main 2=branch [1]: ").strip() != '2'
        _git(cwd, 'add', target or '-A'); r = _git(cwd, 'commit', '-m', msg)
        r.returncode == 0 and print(f"✓ Committed: {msg}")
        if to_main:
            main = _git_main(proj); _git(proj, 'fetch', 'origin', env=env)
            ahead = _git(proj, 'rev-list', '--count', f'origin/{main}..{main}').stdout.strip()
            if ahead and int(ahead) > 0:
                ol = set(_git(cwd, 'diff', '--name-only', f'origin/{main}...HEAD').stdout.split()) & set(_git(proj, 'diff', '--name-only', f'origin/{main}..{main}').stdout.split()) - {''}
                msg = f"[i] {main} {ahead} ahead (different files)\nMerge?" if not ol else f"! {main} {ahead} ahead, overlap: {', '.join(ol)}\n{_git(proj, 'log', f'origin/{main}..{main}', '--oneline').stdout.strip()}\nContinue?"
                skip or input(f"{msg} (y/n): ").lower() in ['y', 'yes'] or _die("x Cancelled")
            _git(proj, 'checkout', main).returncode == 0 or _die(f"x Checkout {main} failed")
            _git(proj, 'merge', wt_branch, '--no-edit', '-X', 'theirs').returncode == 0 or _die("x Merge failed")
            print(f"✓ Merged {wt_branch} -> {main}"); _git_push(proj, main, env) or sys.exit(1)
            _git(proj, 'fetch', 'origin', env=env); _git(proj, 'reset', '--hard', f'origin/{main}')
            if not skip and input(f"\nDelete worktree '{wt_name}'? (y/n): ").strip().lower() in ['y', 'yes']:
                _git(proj, 'worktree', 'remove', '--force', cwd); _git(proj, 'branch', '-D', f'wt-{wt_name}')
                os.path.exists(cwd) and shutil.rmtree(cwd); print("✓ Cleaned up worktree")
                os.chdir(proj); os.execvp(os.environ.get('SHELL', 'bash'), [os.environ.get('SHELL', 'bash')])
        else: _git(cwd, 'push', '-u', 'origin', wt_branch, env=env) and print(f"✓ Pushed to {wt_branch}")
    else:
        cur, main = _git(cwd, 'branch', '--show-current').stdout.strip(), _git_main(cwd)
        _git(cwd, 'add', target or '-A'); r = _git(cwd, 'commit', '-m', msg)
        if r.returncode == 0: print(f"✓ Committed: {msg}")
        elif 'nothing to commit' in r.stdout:
            if _git(cwd, 'remote').stdout.strip() and _git(cwd, 'rev-list', '--count', f'origin/{main}..HEAD').stdout.strip() == '0': print("[i] No changes"); sys.exit(0)
        else: _die(f"Commit failed: {r.stderr.strip() or r.stdout.strip()}")
        if cur != main:
            _git(cwd, 'checkout', main).returncode == 0 or _die(f"x Checkout failed")
            _git(cwd, 'merge', cur, '--no-edit', '-X', 'theirs').returncode == 0 or _die("x Merge failed"); print(f"✓ Merged {cur} -> {main}")
        if not _git(cwd, 'remote').stdout.strip(): print("[i] Local only"); return
        _git(cwd, 'fetch', 'origin', env=env); _git_push(cwd, main, env) or sys.exit(1)

def cmd_pull():
    cwd = os.getcwd(); _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("x Not a git repo")
    env = get_noninteractive_git_env(); _git(cwd, 'fetch', 'origin', env=env)
    ref = 'origin/main' if _git(cwd, 'rev-parse', '--verify', 'origin/main').returncode == 0 else 'origin/master'
    info = _git(cwd, 'log', '-1', '--format=%h %s', ref).stdout.strip()
    print(f"! DELETE local changes -> {info}")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").strip().lower() in ['y', 'yes']) or _die("x Cancelled")
    _git(cwd, 'reset', '--hard', ref); _git(cwd, 'clean', '-f', '-d'); print(f"✓ Synced: {info}")

def cmd_revert():
    cwd = os.getcwd(); _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("x Not a git repo")
    n = int(work_dir_arg) if work_dir_arg and work_dir_arg.isdigit() else 1
    r = _git(cwd, 'revert', 'HEAD', '--no-edit') if n == 1 else _git(cwd, 'revert', f'HEAD~{n}..HEAD', '--no-edit')
    print(f"✓ Reverted {n} commit(s)") if r.returncode == 0 else _die(f"x Revert failed: {r.stderr.strip()}")

def cmd_install():
    bin_dir, script_path = os.path.expanduser("~/.local/bin"), os.path.realpath(__file__)
    os.makedirs(bin_dir, exist_ok=True)
    aio_link = os.path.join(bin_dir, "aio")
    if os.path.islink(aio_link): os.remove(aio_link)
    elif os.path.exists(aio_link): _die(f"x {aio_link} exists but is not a symlink")
    os.symlink(script_path, aio_link); print(f"✓ Symlink: {aio_link}")
    # Termux RunCommandService setup
    if os.environ.get('TERMUX_VERSION') or os.path.exists('/data/data/com.termux'):
        print("\nTermux detected - configuring RunCommandService...")
        termux_dir = os.path.expanduser("~/.termux")
        termux_props = os.path.join(termux_dir, "termux.properties")
        os.makedirs(termux_dir, exist_ok=True)
        prop_content = Path(termux_props).read_text() if os.path.exists(termux_props) else ""
        # Check for uncommented active setting (not just the commented template)
        has_active = any(l.strip().startswith("allow-external-apps") and not l.strip().startswith("#") for l in prop_content.split('\n'))
        if not has_active:
            with open(termux_props, "a") as f: f.write("\nallow-external-apps = true\n")
            print("✓ Added allow-external-apps = true")
        else: print("✓ allow-external-apps already configured")
        if shutil.which('termux-reload-settings'):
            sp.run(['termux-reload-settings']); print("✓ Reloaded Termux settings")
        else: print("! Run: termux-reload-settings")
        print("\nAndroid app setup required:")
        print("   1. Add to AndroidManifest.xml:")
        print('      <uses-permission android:name="com.termux.permission.RUN_COMMAND" />')
        print("   2. Grant permission in Android Settings:")
        print("      Settings -> Apps -> Your App -> Permissions -> Run Termux commands")
    nv = int(sp.run(['node','-v'], capture_output=True, text=True).stdout.strip().lstrip('v').split('.')[0]) if shutil.which('node') else 0
    if nv < 25: print(f"! Node.js {'v'+str(nv) if nv else 'missing'} - run 'aio deps' (fixes Claude V8 crashes)")
    shell = os.environ.get('SHELL', '/bin/bash')
    rc = os.path.expanduser('~/.config/fish/config.fish' if 'fish' in shell else ('~/.zshrc' if 'zsh' in shell else '~/.bashrc'))
    func = '''# aio instant startup
aio() { local d="${1/#~/$HOME}"; [[ -d "$d" ]] && { cd "$d"; ls; return; }; command python3 ~/.local/bin/aio "$@"; }''' if 'fish' not in shell else '''function aio; command python3 ~/.local/bin/aio $argv; end'''
    if 'aio' not in (Path(rc).read_text() if os.path.exists(rc) else ''):
        try:
            if input(f"Add to {rc}? [Y/n]: ").strip().lower() != 'n': Path(rc).open('a').write(func + '\n'); print(f"✓ Added")
        except: pass
    def _ok(p):
        try: return bool(shutil.which(p)) if p in 'tmux wl-copy npm codex claude gemini aider'.split() else (__import__(p), True)[1]
        except: return False
    _a, _n, _p = {'pexpect': 'python3-pexpect', 'prompt_toolkit': 'python3-prompt-toolkit', 'tmux': 'tmux', 'wl-copy': 'wl-clipboard'}, {'codex': '@openai/codex', 'claude': '@anthropic-ai/claude-code', 'gemini': '@google/gemini-cli'}, {'aider': 'aider-chat'}
    ok, am, nm, pm = [p for p in list(_a)+list(_n)+list(_p)+['npm'] if _ok(p)], ' '.join(_a[p] for p in _a if not _ok(p)), ' '.join(_n[p] for p in _n if not _ok(p)), ' '.join(_p[p] for p in _p if not _ok(p))
    ok and print(f"✓ Have: {', '.join(ok)}")
    cmds = [f"sudo apt install {am}" for _ in [1] if am and shutil.which('apt-get')] + [f"sudo npm install -g {nm}" for _ in [1] if nm] + [f"pip install {pm}" for _ in [1] if pm]
    cmds and print(f"\nRun:\n  {' && '.join(cmds)}")
    with WALManager(DB_PATH) as c:
        v = (c.execute("SELECT value FROM config WHERE key='tmux_conf'").fetchone() or [''])[0]
        if v == 'y' or (v != 'n' and input("Enable aio tmux config? (appends to ~/.tmux.conf) [Y/n]: ").strip().lower() != 'n'): _write_tmux_conf(); c.execute("INSERT OR REPLACE INTO config VALUES ('tmux_conf', 'y')"); c.commit(); print("✓ ~/.aios/tmux.conf")
        elif v == '': c.execute("INSERT OR REPLACE INTO config VALUES ('tmux_conf', 'n')"); c.commit()

def cmd_deps():
    print("Installing deps...\n")
    _run = lambda c: sp.run(c, shell=True, capture_output=True).returncode == 0
    _sudo = '' if os.environ.get('TERMUX_VERSION') or os.path.exists('/data/data/com.termux') else 'sudo '
    # Python deps
    for p, apt in [('pexpect', 'python3-pexpect'), ('prompt_toolkit', 'python3-prompt-toolkit')]:
        try: __import__(p); ok = True
        except: ok = _run(f'{_sudo}apt-get install -y {apt}') or _run(f'{sys.executable} -m pip install --user {p}')
        print(f"{'✓' if ok else 'x'} {p}")
    # tmux
    ok = shutil.which('tmux') or _run(f'{_sudo}apt-get install -y tmux') or _run('brew install tmux') or _run('pkg install -y tmux')
    print(f"{'✓' if shutil.which('tmux') else 'x'} tmux")
    # Node.js via n - bootstrap if needed, upgrade if < 25
    shutil.which('npm') or _run(f'{_sudo}apt-get install -y nodejs npm') or _run('brew install node') or _run('pkg install -y nodejs')
    nv = int(sp.run(['node','-v'], capture_output=True, text=True).stdout.strip().lstrip('v').split('.')[0]) if shutil.which('node') else 0
    if nv < 25: print(f"! Node v{nv} -> latest..."); print(f"{'✓' if _run(f'{_sudo}npm i -g n && {_sudo}n latest') else 'x'} node")
    else: print(f"✓ node v{nv}")
    # AI agents
    for cmd, pkg in [('codex','@openai/codex'), ('claude','@anthropic-ai/claude-code'), ('gemini','@google/gemini-cli')]:
        shutil.which(cmd) or _run(f'{_sudo}npm i -g {pkg}')
        print(f"{'✓' if shutil.which(cmd) else 'x'} {cmd}")
    shutil.which('aider') or _run(f'{sys.executable} -m pip install --user aider-chat'); print(f"{'✓' if shutil.which('aider') else 'x'} aider")
    print("\n✓ Done!")

def cmd_prompt():
    name = work_dir_arg or 'feat'
    prompt_file = PROMPTS_DIR / f'{name}.txt'
    if not prompt_file.exists(): print(f"Prompts dir: {PROMPTS_DIR}\nAvailable: {', '.join(p.stem for p in PROMPTS_DIR.glob('*.txt'))}"); sys.exit(1)
    print(f"Editing: {prompt_file}")
    current = prompt_file.read_text().strip()
    new_val = input_box(current, f"Edit '{name}' (Ctrl+D to save, Ctrl+C to cancel)")
    if new_val is None: print("Cancelled")
    elif new_val.strip() != current: prompt_file.write_text(new_val.strip()); print(f"✓ Saved")
    else: print("No changes")

def cmd_gdrive():
    import aioCloud
    if work_dir_arg == 'login': aioCloud.configured() and not _confirm("Already logged in. Switch?") or aioCloud.login()
    elif work_dir_arg == 'logout': aioCloud.logout()
    else: aioCloud.status()

def cmd_note():
    ND = Path(DATA_DIR) / 'notebook'; AD = ND / 'archive'; raw = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    def _sync(m='update'): sp.Popen(f'git -C "{ND}" rev-parse --git-dir >/dev/null 2>&1 && git -C "{ND}" add -A && git -C "{ND}" commit -m "{m}" && git -C "{ND}" push', shell=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    if _git(ND, 'rev-parse', '--git-dir').returncode != 0: sp.run(['gh', 'repo', 'clone', 'notebook', str(ND)], capture_output=True).returncode == 0 or _confirm('Create GitHub notebook?') and (ND.mkdir(parents=True, exist_ok=True), _git(ND, 'init', '-b', 'main'), Path(ND/'.gitkeep').touch(), _git(ND, 'add', '.'), _git(ND, 'commit', '-m', 'init'), sp.run(['gh', 'repo', 'create', 'notebook', '--private', '--source', str(ND), '--push'], timeout=60)) or ND.mkdir(parents=True, exist_ok=True)
    gh = bool(_git(ND, 'remote', '-v').stdout.strip())
    if raw and raw != 'ls' and not raw.isdigit(): gh and _git(ND, 'pull', '--rebase', '-q'); slug = re.sub(r'[^\w\-]', '', raw.split('\n')[0][:40].lower().replace(' ', '-'))[:30] or 'note'; (ND / f"{slug}-{datetime.now().strftime('%m%d%H%M')}.md").write_text(raw); _sync(f'add {slug}'); print("✓ github" if gh else "✓ local"); return
    _git(ND, 'pull', '--rebase'); _git(ND, 'status', '--porcelain').stdout.strip() and _sync('migrate'); print(f"📓 {ND} [{'github' if gh else 'local'}]")
    def _notes(): return sorted([n for n in ND.glob('*.md')], key=lambda p: p.name, reverse=True)
    def _arch(n): AD.mkdir(exist_ok=True); shutil.move(str(n), str(AD / n.name)); _sync(f'archive {n.name}')
    notes = _notes()
    if not notes: print("No notes. Create: aio note <content>"); return
    if raw == 'ls': [print(f"{i}. {n.read_text().split(chr(10))[0][:60]}") for i, n in enumerate(notes)]; return
    if raw and raw.isdigit() and int(raw) < len(notes): print(notes[int(raw)].read_text()); return
    print(f"─ {len(notes)} notes ─ [a]rchive [m]ore [enter]next [q]uit")
    for n in notes:
        print(f"\n{n.read_text()[:500]}"); ch = input("> ").strip().lower()
        if ch == 'a': _arch(n); print("✓ github" if gh else "✓ local")
        elif ch == 'm': mc=input(f"  {'[c]loud sync' if not gh else '[synced]'} [b]ack: ").lower(); mc=='c' and not gh and _confirm("Sync to GitHub?") and print("✓ cloud" if sp.run(['gh','repo','create','notebook','--private','--source',str(ND),'--push'],capture_output=True,timeout=60).returncode==0 or (_git(ND,'remote','add','origin',f"https://github.com/{sp.run(['gh','api','user','-q','.login'],capture_output=True,text=True).stdout.strip()}/notebook.git"), _git(ND,'fetch','origin'), _git(ND,'pull','--rebase','--allow-unrelated-histories','origin','main'), _git(ND,'push','-u','origin','main'))[-1].returncode==0 else "x failed")
        elif ch == 'q': break

def cmd_add():
    args = [a for a in sys.argv[2:] if a != '--global']
    is_global = '--global' in sys.argv[2:]
    if len(args) >= 2 and not os.path.isdir(os.path.expanduser(args[0])):
        interpreters = ['python', 'python3', 'node', 'npm', 'ruby', 'perl', 'java', 'go', 'sh', 'bash', 'npx']
        if args[0] in interpreters:
            cmd_val = ' '.join(args); print(f"Command: {cmd_val}")
            cmd_name = input("Name for this command: ").strip()
            if not cmd_name: print("x Cancelled"); sys.exit(1)
        else: cmd_name, cmd_val = args[0], ' '.join(args[1:])
        cwd, home = os.getcwd(), os.path.expanduser('~')
        if not is_global and cwd != home and not cmd_val.startswith('cd '): cmd_val = f"cd {cwd.replace(home, '~')} && {cmd_val}"
        ok, msg = add_app(cmd_name, cmd_val); print(f"{'✓' if ok else 'x'} {msg}")
        if ok: auto_backup_check(); list_all_items()
        sys.exit(0 if ok else 1)
    path = os.path.abspath(os.path.expanduser(args[0])) if args else os.getcwd()
    ok, msg = add_project(path); print(f"{'✓' if ok else 'x'} {msg}")
    if ok: auto_backup_check(); list_all_items()
    sys.exit(0 if ok else 1)

def cmd_remove():
    if not work_dir_arg: print("Usage: aio remove <#|name>\n"); list_all_items(); sys.exit(0)
    projects, apps = load_projects(), load_apps()
    if work_dir_arg.isdigit():
        idx = int(work_dir_arg)
        if idx < len(projects): ok, msg = remove_project(idx)
        elif idx < len(projects) + len(apps): ok, msg = remove_app(idx - len(projects))
        else: print(f"x Invalid index: {idx}"); list_all_items(); sys.exit(1)
    else:
        app_idx = next((i for i, (n, _) in enumerate(apps) if n.lower() == work_dir_arg.lower()), None)
        if app_idx is None: print(f"x Not found: {work_dir_arg}"); list_all_items(); sys.exit(1)
        ok, msg = remove_app(app_idx)
    print(f"{'✓' if ok else 'x'} {msg}")
    if ok: auto_backup_check(); list_all_items()
    sys.exit(0 if ok else 1)

def cmd_dash():
    if not sm.has_session('dash'): sp.run(['tmux', 'new-session', '-d', '-s', 'dash', '-c', work_dir]); sp.run(['tmux', 'split-window', '-h', '-t', 'dash', '-c', work_dir, 'sh -c "aio jobs; exec $SHELL"'])
    os.execvp('tmux', ['tmux', 'switch-client' if 'TMUX' in os.environ else 'attach', '-t', 'dash'])

def cmd_fix_bug_feat_auto_del():
    args, agent = sys.argv[2:], 'l'
    if args and args[0] in 'clg': agent, args = args[0], args[1:]
    pt = get_prompt(arg, show_location=True) or '{task}'
    task = 'autonomous' if arg in ('fix', 'auto', 'del') else (' '.join(args) if args else input(f"{arg}: "))
    an, cmd = sessions[agent]; sn = f"{arg}-{agent}-{datetime.now().strftime('%H%M%S')}"; prompt = pt if arg in ('fix', 'auto', 'del') else pt.format(task=task)
    pre = get_agent_prefix(an); full_prompt = (pre if pre and not prompt.startswith(pre.strip()) else '') + prompt
    print(f"{arg.upper()} [{an}]: {task[:50]}{'...' if len(task) > 50 else ''}")
    create_tmux_session(sn, os.getcwd(), f"{cmd} {shlex.quote(full_prompt)}")
    launch_in_new_window(sn) if 'TMUX' in os.environ else os.execvp(sm.attach(sn)[0], sm.attach(sn))

def cmd_multi():
    if work_dir_arg == 'set':
        ns = ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else ''
        if not ns: print(f"Current: {load_config().get('multi_default', 'c:3')}"); sys.exit(0)
        if not parse_agent_specs_and_prompt([''] + ns.split(), 1)[0]: _die(f"Invalid: {ns}")
        with WALManager(DB_PATH) as c: c.execute("INSERT OR REPLACE INTO config VALUES ('multi_default', ?)", (ns,)); c.commit(); print(f"✓ Default: {ns}"); sys.exit(0)
    project_path, start = (PROJECTS[int(work_dir_arg)], 3) if work_dir_arg and work_dir_arg.isdigit() and int(work_dir_arg) < len(PROJECTS) else (os.getcwd(), 2)
    agent_specs, _, _ = parse_agent_specs_and_prompt(sys.argv, start)
    if not agent_specs: ds = load_config().get('multi_default', 'l:3'); agent_specs, _, _ = parse_agent_specs_and_prompt([''] + ds.split(), 1); print(f"Using: {ds}")
    total, repo_name, run_id = sum(c for _, c in agent_specs), os.path.basename(project_path), datetime.now().strftime('%Y%m%d-%H%M%S')
    sn, run_dir = f"{repo_name}-{run_id}", os.path.join(WORKTREES_DIR, repo_name, run_id)
    cd = os.path.join(run_dir, "candidates"); os.makedirs(cd, exist_ok=True)
    with open(os.path.join(run_dir, "run.json"), "w") as f: json.dump({"agents": [f"{k}:{c}" for k, c in agent_specs], "created": run_id, "repo": project_path}, f)
    with WALManager(DB_PATH) as c: c.execute("INSERT OR REPLACE INTO multi_runs VALUES (?, ?, '', ?, 'running', CURRENT_TIMESTAMP, NULL)", (run_id, project_path, json.dumps([f"{k}:{c}" for k, c in agent_specs]))); c.commit()
    print(f"{total} agents in {repo_name}/{run_id}..."); env, launched, an = get_noninteractive_git_env(), [], {}
    for ak, cnt in agent_specs:
        bn, bc = sessions.get(ak, (None, None))
        if not bn: continue
        for i in range(cnt):
            an[bn] = an.get(bn, 0) + 1; aid = f"{ak}{i}"; wt = os.path.join(cd, aid)
            sp.run(['git', '-C', project_path, 'worktree', 'add', '-b', f'wt-{repo_name}-{run_id}-{aid}', wt], capture_output=True, env=env)
            if os.path.exists(wt): launched.append((wt, bc)); print(f"✓ {bn}-{an[bn]}")
    if not launched: print("x No agents created"); sys.exit(1)
    sp.run(['tmux', 'new-session', '-d', '-s', sn, '-c', launched[0][0], launched[0][1]], env=env)
    for wt, bc in launched[1:]: sp.run(['tmux', 'split-window', '-h', '-t', sn, '-c', wt, bc], env=env)
    sp.run(['tmux', 'split-window', '-h', '-t', sn, '-c', cd], env=env); sp.run(['tmux', 'send-keys', '-t', sn, f'n={len(launched)}; while read -ep "> " c; do [ -n "$c" ] && for i in $(seq 0 $((n-1))); do tmux send-keys -l -t ":.$i" "$c"; tmux send-keys -t ":.$i" C-m; done; done', 'C-m'])
    sp.run(['tmux', 'select-layout', '-t', sn, 'even-horizontal'], env=env); ensure_tmux_options()
    print(f"\n+ '{sn}': {len(launched)}+broadcast"); print(f"   tmux switch-client -t {sn}") if "TMUX" in os.environ else os.execvp('tmux', ['tmux', 'attach', '-t', sn])

def cmd_tree():
    proj = PROJECTS[int(work_dir_arg)] if work_dir_arg and work_dir_arg.isdigit() and int(work_dir_arg) < len(PROJECTS) else os.getcwd()
    _git(proj, 'rev-parse', '--git-dir').returncode == 0 or _die("x Not a git repo")
    wp = wt_create(proj, datetime.now().strftime('%Y%m%d-%H%M%S'))
    wp or sys.exit(1)
    os.chdir(wp); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])

def cmd_e():
    if 'TMUX' in os.environ: os.execvp('nvim', ['nvim', '.'])
    else:
        create_tmux_session('edit', os.getcwd(), 'nvim .')
        os.execvp('tmux', ['tmux', 'attach', '-t', 'edit'])

def cmd_x(): sp.run(['tmux', 'kill-server']); print("✓ All sessions killed")
def cmd_p(): list_all_items(show_help=False)
def cmd_copy():
    L=os.popen('tmux capture-pane -pJ -S -99').read().split('\n') if os.environ.get('TMUX') else []; P=[i for i,l in enumerate(L) if '$'in l and'@'in l]; u=next((i for i in reversed(P) if 'copy'in L[i]),len(L)); p=next((i for i in reversed(P) if i<u),-1); full='\n'.join(L[p+1:u]).strip() if P else ''; sp.run(_get_clipboard_cmd(),shell=True,input=full,text=True); s=full.replace('\n',' '); print(f"✓ {s[:23]+'...'+s[-24:] if len(s)>50 else s}")

def cmd_worktree_plus():
    key = arg[:-2]
    if key not in sessions: print(f"x Unknown session key: {key}"); return
    proj = PROJECTS[int(work_dir_arg)] if work_dir_arg and work_dir_arg.isdigit() and int(work_dir_arg) < len(PROJECTS) else work_dir
    base_name, cmd = sessions[key]
    wp = wt_create(proj, f"{base_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    if not wp: return
    sn = os.path.basename(wp); create_tmux_session(sn, wp, cmd, env=get_noninteractive_git_env(), capture_output=False)
    send_prefix(sn, base_name, wp)
    if new_window: launch_in_new_window(sn)
    elif "TMUX" in os.environ: print(f"✓ Session: {sn}")
    else: os.execvp(sm.attach(sn)[0], sm.attach(sn))

def cmd_dir_or_file():
    if os.path.isdir(os.path.expanduser(arg)):
        d = os.path.expanduser('~' + arg) if arg.startswith('/projects/') else os.path.expanduser(arg)
        print(f"{d}", flush=True); sp.run(['ls', d])
    elif os.path.isfile(arg):
        ext = os.path.splitext(arg)[1].lower()
        if ext == '.py': os.execvp(sys.executable, [sys.executable, arg] + sys.argv[2:])
        elif ext in ('.html', '.htm'): __import__('webbrowser').open('file://' + os.path.abspath(arg))
        elif ext == '.md': os.execvp(os.environ.get('EDITOR', 'nvim'), [os.environ.get('EDITOR', 'nvim'), arg])

def cmd_session():
    # Inside tmux - always create new pane (allows multiple agents in parallel)
    if 'TMUX' in os.environ and arg in sessions and len(arg) == 1:
        an, cmd = sessions[arg]; pid = sp.run(['tmux', 'split-window', '-bvP', '-F', '#{pane_id}', '-c', work_dir, cmd], capture_output=True, text=True).stdout.strip()
        pid and (sp.run(['tmux', 'split-window', '-v', '-t', pid, '-c', work_dir, 'sh -c "ls;exec $SHELL"']), sp.run(['tmux', 'select-pane', '-t', pid]))
        pid and send_prefix(pid, an, work_dir)
        sys.exit(0)
    # Ghost claiming (outside tmux only - claim pre-warmed session)
    if arg in _GHOST_MAP and not work_dir_arg and (g := _ghost_claim(arg, work_dir)):
        sn = f"{sessions[arg][0] if arg in sessions else arg}-{os.path.basename(work_dir)}"; sp.run(['tmux', 'rename-session', '-t', g, sn], capture_output=True); print(f"Ghost: {sn}"); os.execvp('tmux', ['tmux', 'attach', '-t', sn])
    sn = get_or_create_directory_session(arg, work_dir); env = get_noninteractive_git_env(); created = False
    if sn is None: n, c = sessions.get(arg, (arg, None)); create_tmux_session(n, work_dir, c or arg, env=env); sn = n; created = True
    elif not sm.has_session(sn): create_tmux_session(sn, work_dir, sessions[arg][1], env=env); created = True
    is_p = arg.endswith('p') and not arg.endswith('pp') and len(arg) == 2 and arg in sessions
    pp = [a for a in sys.argv[(2 if is_work_dir_a_prompt else (3 if work_dir_arg else 2)):] if a not in ['-w', '--new-window', '--yes', '-y', '-t', '--with-terminal']]
    if pp: print("Prompt queued"); sp.Popen([sys.executable, __file__, 'send', sn, ' '.join(pp)] + (['--no-enter'] if is_p else []), stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif is_p and (pm := {'cp': CODEX_PROMPT, 'lp': CLAUDE_PROMPT, 'gp': GEMINI_PROMPT}.get(arg)): sp.Popen([sys.executable, __file__, 'send', sn, pm, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif created and arg in sessions: send_prefix(sn, sessions[arg][0], work_dir)
    if new_window: launch_in_new_window(sn); with_terminal and launch_terminal_in_dir(work_dir)
    elif "TMUX" in os.environ or not sys.stdout.isatty(): print(f"✓ Session: {sn}")
    else: os.execvp(sm.attach(sn)[0], sm.attach(sn))

def cmd_settings():
    f=sys.argv[2]if len(sys.argv)>2 else None;p=Path(DATA_DIR)/f if f else None;v=sys.argv[3]if len(sys.argv)>3 else None
    if not f:s="on"if(Path(DATA_DIR)/'n').exists()else"off";print(f"1. n [{s}] commands without aio prefix\n   aio set n {'off'if s=='on'else'on'}");return
    if v=='on':p.touch();print(f"✓ on - open new terminal tab")
    elif v=='off':p.unlink(missing_ok=True);print(f"✓ off - open new terminal tab")
    else:print("on"if p.exists()else"off")

# Command dispatch
COMMANDS = {
    None: cmd_help, '': cmd_help, 'help': cmd_help_full, 'hel': cmd_help_full, '--help': cmd_help_full, '-h': cmd_help_full,
    'update': cmd_update, 'upd': cmd_update, 'jobs': cmd_jobs, 'job': cmd_jobs, 'kill': cmd_kill, 'kil': cmd_kill, 'killall': cmd_kill, 'attach': cmd_attach, 'att': cmd_attach,
    'cleanup': cmd_cleanup, 'cle': cmd_cleanup, 'config': cmd_config, 'con': cmd_config, 'ls': cmd_ls, 'diff': cmd_diff, 'dif': cmd_diff, 'send': cmd_send, 'sen': cmd_send,
    'watch': cmd_watch, 'wat': cmd_watch, 'push': cmd_push, 'pus': cmd_push, 'pull': cmd_pull, 'pul': cmd_pull, 'revert': cmd_revert, 'rev': cmd_revert, 'set': cmd_settings,
    'install': cmd_install, 'ins': cmd_install, 'deps': cmd_deps, 'dep': cmd_deps, 'prompt': cmd_prompt, 'pro': cmd_prompt, 'gdrive': cmd_gdrive, 'gdr': cmd_gdrive, 'note': cmd_note, 'n': cmd_note, 'settings': cmd_settings,
    'add': cmd_add, 'remove': cmd_remove, 'rem': cmd_remove, 'rm': cmd_remove, 'dash': cmd_dash, 'das': cmd_dash, 'all': cmd_multi,
    'e': cmd_e, 'x': cmd_x, 'p': cmd_p, 'copy': cmd_copy, 'cop': cmd_copy, 'tree': cmd_tree, 'tre': cmd_tree, 'dir': lambda: (print(f"{os.getcwd()}"), sp.run(['ls'])),
    'fix': cmd_fix_bug_feat_auto_del, 'bug': cmd_fix_bug_feat_auto_del, 'feat': cmd_fix_bug_feat_auto_del, 'fea': cmd_fix_bug_feat_auto_del,
    'auto': cmd_fix_bug_feat_auto_del, 'aut': cmd_fix_bug_feat_auto_del, 'del': cmd_fix_bug_feat_auto_del,
}

if arg in COMMANDS: COMMANDS[arg]()
elif arg and arg.endswith('++') and not arg.startswith('w'): cmd_worktree_plus()
elif arg and (os.path.isdir(os.path.expanduser(arg)) or os.path.isfile(arg) or (arg.startswith('/projects/') and os.path.isdir(os.path.expanduser('~' + arg)))): cmd_dir_or_file()
elif arg in sessions or (arg and len(arg) <= 3): cmd_session()
else: cmd_session()
