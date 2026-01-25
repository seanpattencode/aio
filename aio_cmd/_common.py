"""Shared utilities for aio commands - like git's libgit"""
import sys, os, subprocess as sp, sqlite3, json, shutil, time, re, socket
from datetime import datetime
from pathlib import Path

# Constants
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PROMPTS_DIR = Path(SCRIPT_DIR) / 'data' / 'prompts'
DATA_DIR = os.path.expanduser("~/.local/share/aios")
DB_PATH = os.path.join(DATA_DIR, "aio.db")
EVENTS_PATH = os.path.join(DATA_DIR, "events.jsonl")
NOTE_DIR = os.path.join(DATA_DIR, "notebook")
LOG_DIR = os.path.join(DATA_DIR, "logs")
DEVICE_ID = (sp.run(['getprop','ro.product.model'],capture_output=True,text=True).stdout.strip().replace(' ','-') or socket.gethostname()) if os.path.exists('/data/data/com.termux') else socket.gethostname()
_GP, _GT = '_aio_ghost_', 300
_GM = {'c': 'l', 'l': 'l', 'g': 'g', 'o': 'l', 'co': 'c', 'cp': 'c', 'lp': 'l', 'gp': 'g'}
_AIO_DIR = os.path.expanduser('~/.aios')
_AIO_CONF = os.path.join(_AIO_DIR, 'tmux.conf')
_USER_CONF = os.path.expanduser('~/.tmux.conf')
_SRC_LINE = 'source-file ~/.aios/tmux.conf  # aio'
RCLONE_REMOTE, RCLONE_BACKUP_PATH = 'aio-gdrive', 'aio-backup'

# Basic helpers
def _git(path, *a, **k): return sp.run(['git', '-C', path] + list(a), capture_output=True, text=True, **k)
def _tmux(*a): return sp.run(['tmux'] + list(a), capture_output=True, text=True)
def _ok(m): print(f"✓ {m}")
def _err(m): print(f"x {m}")
def _die(m, c=1): _err(m); sys.exit(c)
def _confirm(m): return input(f"{m} (y/n): ").strip().lower() in ['y', 'yes']
def _up(h): return not (lambda s,hp: s.settimeout(0.5) or s.connect_ex((hp[0].split('@')[-1], int(hp[1]) if len(hp)>1 else 22)))(socket.socket(), h.rsplit(':',1))

# Tmux wrapper
class TM:
    def __init__(self): self._v = None
    def new(self, n, d, c, e=None): return sp.run(['tmux', 'new-session', '-d', '-s', n, '-c', d] + ([c] if c else []), capture_output=True, env=e)
    def send(self, n, t): return sp.run(['tmux', 'send-keys', '-l', '-t', n, t])
    def attach(self, n): return ['tmux', 'attach', '-t', n]
    def has(self, n):
        try: return sp.run(['tmux', 'has-session', '-t', n], capture_output=True, timeout=2).returncode == 0
        except sp.TimeoutExpired: return (sp.run(['pkill', '-9', 'tmux']), False)[1] if input("! tmux hung. Kill? (y/n): ").lower() == 'y' else sys.exit(1)
    def ls(self): return _tmux('list-sessions', '-F', '#{session_name}')
    def cap(self, n): return _tmux('capture-pane', '-p', '-t', n)
    @property
    def ver(self):
        if self._v is None: self._v = sp.check_output(['tmux', '-V'], text=True).split()[1] if shutil.which('tmux') else '0'
        return self._v
tm = TM()

# Git helpers
def _sg(*a, **k): return sp.run(['git', '-C', SCRIPT_DIR] + list(a), capture_output=True, text=True, **k)
def _git_main(p):
    r = _git(p, 'symbolic-ref', 'refs/remotes/origin/HEAD')
    return r.stdout.strip().replace('refs/remotes/origin/', '') if r.returncode == 0 else ('main' if _git(p, 'rev-parse', '--verify', 'main').returncode == 0 else 'master')
def _git_push(p, b, env, force=False):
    r = _git(p, 'push', *(['--force'] if force else []), 'origin', b, env=env)
    if r.returncode == 0: print(f"✓ Pushed to {b}"); return True
    err = r.stderr.strip() or r.stdout.strip()
    if 'non-fast-forward' in err and input("! Force push? (y/n): ").lower() in ['y', 'yes']:
        _git(p, 'fetch', 'origin', env=env); return _git_push(p, b, env, True)
    print(f"x Push failed: {err}"); return False
def _env():
    e = os.environ.copy(); e.pop('DISPLAY', None); e.pop('GPG_AGENT_INFO', None); e['GIT_TERMINAL_PROMPT'] = '0'
    return e
def ensure_git_cfg():
    n, e = sp.run(['git', 'config', 'user.name'], capture_output=True, text=True), sp.run(['git', 'config', 'user.email'], capture_output=True, text=True)
    if n.returncode == 0 and e.returncode == 0 and n.stdout.strip() and e.stdout.strip(): return True
    if not shutil.which('gh'): return False
    try:
        r = sp.run(['gh', 'api', 'user'], capture_output=True, text=True)
        if r.returncode != 0: return False
        u = json.loads(r.stdout); gn, gl = u.get('name') or u.get('login', ''), u.get('login', '')
        ge = u.get('email') or f"{gl}@users.noreply.github.com"
        gn and not n.stdout.strip() and sp.run(['git', 'config', '--global', 'user.name', gn], capture_output=True)
        ge and not e.stdout.strip() and sp.run(['git', 'config', '--global', 'user.email', ge], capture_output=True)
        return True
    except: return False

# Database
def db(): c = sqlite3.connect(DB_PATH); c.execute("PRAGMA journal_mode=WAL;"); return c

def get_prompt(name, show=False):
    pf = PROMPTS_DIR / f'{name}.txt'
    if pf.exists():
        show and print(f"Prompt: {pf}")
        return pf.read_text().strip()
    return None

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, display_order INTEGER NOT NULL, device TEXT DEFAULT '*')")
        c.execute("CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, command TEXT NOT NULL, display_order INTEGER NOT NULL, device TEXT DEFAULT '*')")
        for t in ['projects', 'apps']:
            if 'device' not in [r[1] for r in c.execute(f"PRAGMA table_info({t})")]: c.execute(f"ALTER TABLE {t} ADD COLUMN device TEXT DEFAULT '*'")
        c.execute("CREATE TABLE IF NOT EXISTS sessions (key TEXT PRIMARY KEY, name TEXT NOT NULL, command_template TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS multi_runs (id TEXT PRIMARY KEY, repo TEXT NOT NULL, prompt TEXT NOT NULL, agents TEXT NOT NULL, status TEXT DEFAULT 'running', created_at TEXT DEFAULT CURRENT_TIMESTAMP, review_rank TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, t TEXT, s INTEGER DEFAULT 0, d TEXT, c TEXT DEFAULT CURRENT_TIMESTAMP, proj TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS note_projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, c TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, real_deadline INTEGER NOT NULL, virtual_deadline INTEGER, created_at INTEGER NOT NULL, completed_at INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS jobs (name TEXT PRIMARY KEY, step TEXT NOT NULL, status TEXT NOT NULL, path TEXT, session TEXT, updated_at INTEGER NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS hub_jobs (id INTEGER PRIMARY KEY, name TEXT, schedule TEXT, prompt TEXT, agent TEXT DEFAULT 'l', project TEXT, device TEXT, enabled INTEGER DEFAULT 1, last_run TEXT, parallel INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS agent_logs (session TEXT PRIMARY KEY, parent TEXT, started REAL, device TEXT)")
        if 'device' not in [r[1] for r in c.execute("PRAGMA table_info(agent_logs)")]: c.execute("ALTER TABLE agent_logs ADD COLUMN device TEXT")
        if c.execute("SELECT COUNT(*) FROM config").fetchone()[0] == 0:
            dp = get_prompt('default') or ''
            for k, v in [('claude_prompt', dp), ('codex_prompt', dp), ('gemini_prompt', dp), ('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees")), ('multi_default', 'l:3')]: c.execute("INSERT INTO config VALUES (?, ?)", (k, v))
        c.execute("INSERT OR IGNORE INTO config VALUES ('multi_default', 'l:3')")
        c.execute("INSERT OR IGNORE INTO config VALUES ('claude_prefix', 'Ultrathink. ')")
        if c.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
            for p in [SCRIPT_DIR, os.path.expanduser("~/aio"), os.path.expanduser("~/projects/aio")]:
                if os.path.isdir(p) and os.path.isdir(os.path.join(p, ".git")): c.execute("INSERT INTO projects (path, display_order, device) VALUES (?, ?, ?)", (p, 0, DEVICE_ID)); break
        if c.execute("SELECT COUNT(*) FROM apps").fetchone()[0] == 0:
            ui = next((p for p in [os.path.join(SCRIPT_DIR, "aioUI.py"), os.path.expanduser("~/aio/aioUI.py"), os.path.expanduser("~/.local/bin/aioUI.py")] if os.path.exists(p)), None)
            if ui: c.execute("INSERT INTO apps (name, command, display_order) VALUES (?, ?, ?)", ("aioUI", f"python3 {ui}", 0))
        if c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0:
            cdx, cld = 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox', 'claude --dangerously-skip-permissions'
            for k, n, t in [('h','htop','htop'),('t','top','top'),('g','gemini','gemini --yolo'),('gemini','gemini','gemini --yolo'),('gp','gemini-p','gemini --yolo "{GEMINI_PROMPT}"'),('c','claude',cld),('claude','claude',cld),('cp','claude-p',f'{cld} "{{CLAUDE_PROMPT}}"'),('l','claude',cld),('lp','claude-p',f'{cld} "{{CLAUDE_PROMPT}}"'),('o','claude',cld),('co','codex',cdx),('codex','codex',cdx),('cop','codex-p',f'{cdx} "{{CODEX_PROMPT}}"'),('a','aider','OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral')]:
                c.execute("INSERT INTO sessions VALUES (?, ?, ?)", (k, n, t))
        c.execute("INSERT OR IGNORE INTO sessions VALUES ('o', 'claude', 'claude --dangerously-skip-permissions')")
        c.execute("INSERT OR IGNORE INTO sessions VALUES ('a', 'aider', 'OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral')")
        c.commit()

def load_cfg():
    with db() as c: return dict(c.execute("SELECT key, value FROM config").fetchall())

def load_proj():
    with db() as c: return [r[0] for r in c.execute("SELECT path FROM projects WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,)).fetchall()]

def load_apps():
    with db() as c: return [(r[0], r[1]) for r in c.execute("SELECT name, command FROM apps WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,))]

def load_sess(cfg):
    with db() as c: data = c.execute("SELECT key, name, command_template FROM sessions").fetchall()
    dp, s = get_prompt('default'), {}
    esc = lambda p: cfg.get(p, dp or '').replace('\n', '\\n').replace('"', '\\"')
    for k, n, t in data:
        s[k] = (n, t.replace(' "{CLAUDE_PROMPT}"', '').replace(' "{CODEX_PROMPT}"', '').replace(' "{GEMINI_PROMPT}"', '') if k in ['cp','lp','gp'] else t.format(CLAUDE_PROMPT=esc('claude_prompt'), CODEX_PROMPT=esc('codex_prompt'), GEMINI_PROMPT=esc('gemini_prompt')))
    return s

def _refresh_cache():
    p, a = load_proj(), load_apps()
    out = [f"PROJECTS:"] + [f"  {i}. {'+' if os.path.exists(x) else 'x'} {x}" for i, x in enumerate(p)]
    out += [f"COMMANDS:"] + [f"  {len(p)+i}. {n} -> {c.replace(os.path.expanduser('~'), '~')[:60]}" for i, (n, c) in enumerate(a)] if a else []
    Path(os.path.join(DATA_DIR, 'help_cache.txt')).write_text(HELP_SHORT + '\n' + '\n'.join(out) + '\n')

def add_proj(p):
    p = os.path.abspath(os.path.expanduser(p))
    if not os.path.isdir(p): return False, f"Not a directory: {p}"
    with db() as c:
        if c.execute("SELECT 1 FROM projects WHERE path=? AND device IN (?, '*')", (p, DEVICE_ID)).fetchone(): return False, f"Exists: {p}"
        m = c.execute("SELECT MAX(display_order) FROM projects").fetchone()[0]
        c.execute("INSERT INTO projects (path, display_order, device) VALUES (?, ?, ?)", (p, 0 if m is None else m+1, DEVICE_ID)); c.commit()
    _refresh_cache(); return True, f"Added: {p}"

def rm_proj(i):
    with db() as c:
        rows = c.execute("SELECT id, path FROM projects WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,)).fetchall()
        if i < 0 or i >= len(rows): return False, f"Invalid index: {i}"
        c.execute("DELETE FROM projects WHERE id=?", (rows[i][0],))
        for j, r in enumerate(c.execute("SELECT id FROM projects WHERE device=? ORDER BY display_order", (DEVICE_ID,))): c.execute("UPDATE projects SET display_order=? WHERE id=?", (j, r[0]))
        c.commit()
    _refresh_cache(); return True, f"Removed: {rows[i][1]}"

def add_app(n, cmd):
    if not n or not cmd: return False, "Name and command required"
    with db() as c:
        if c.execute("SELECT 1 FROM apps WHERE name=? AND device IN (?, '*')", (n, DEVICE_ID)).fetchone(): return False, f"Exists: {n}"
        m = c.execute("SELECT MAX(display_order) FROM apps").fetchone()[0]
        c.execute("INSERT INTO apps (name, command, display_order, device) VALUES (?, ?, ?, ?)", (n, cmd, 0 if m is None else m+1, DEVICE_ID)); c.commit()
    _refresh_cache(); return True, f"Added: {n}"

def rm_app(i):
    with db() as c:
        rows = c.execute("SELECT id, name FROM apps WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,)).fetchall()
        if i < 0 or i >= len(rows): return False, f"Invalid index: {i}"
        c.execute("DELETE FROM apps WHERE id=?", (rows[i][0],))
        for j, r in enumerate(c.execute("SELECT id FROM apps WHERE device=? ORDER BY display_order", (DEVICE_ID,))): c.execute("UPDATE apps SET display_order=? WHERE id=?", (j, r[0]))
        c.commit()
    _refresh_cache(); return True, f"Removed: {rows[i][1]}"

def fmt_cmd(c, mx=60):
    d = c.replace(os.path.expanduser('~'), '~')
    return d[:mx-3] + "..." if len(d) > mx else d

# Cloud sync
def get_rclone(): return shutil.which('rclone') or next((p for p in ['/usr/bin/rclone', os.path.expanduser('~/.local/bin/rclone')] if os.path.isfile(p)), None)
def cloud_configured():
    r = sp.run([get_rclone(), 'listremotes'], capture_output=True, text=True) if get_rclone() else None
    return r and r.returncode == 0 and f'{RCLONE_REMOTE}:' in r.stdout
def cloud_account():
    if not (rc := get_rclone()): return None
    try:
        token = json.loads(json.loads(sp.run([rc, 'config', 'dump'], capture_output=True, text=True).stdout).get(RCLONE_REMOTE, {}).get('token', '{}')).get('access_token')
        if not token: return None
        import urllib.request
        u = json.loads(urllib.request.urlopen(urllib.request.Request('https://www.googleapis.com/drive/v3/about?fields=user', headers={'Authorization': f'Bearer {token}'}), timeout=5).read()).get('user', {})
        return f"{u.get('displayName', '')} <{u.get('emailAddress', 'unknown')}>"
    except: return None
def cloud_sync(wait=False):
    if not (rc := get_rclone()) or not cloud_configured(): return False, None
    local, remote = str(Path(SCRIPT_DIR) / 'data'), f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}'
    def _sync():
        r = sp.run([rc, 'sync', local, remote, '-q'], capture_output=True, text=True)
        ef = Path(DATA_DIR) / '.rclone_err'; ef.write_text(r.stderr) if r.returncode != 0 else ef.unlink(missing_ok=True); return r.returncode == 0
    return (True, _sync()) if wait else (__import__('threading').Thread(target=_sync, daemon=True).start(), (True, None))[1]
def cloud_pull_notes():
    if not (rc := get_rclone()) or not cloud_configured(): return False
    sp.run([rc, 'sync', f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}/notebook', NOTE_DIR, '-q'], capture_output=True)
    return True
def cloud_install():
    import platform
    bd, arch = os.path.expanduser('~/.local/bin'), 'amd64' if platform.machine() in ('x86_64', 'AMD64') else 'arm64'
    print(f"Installing rclone..."); os.makedirs(bd, exist_ok=True)
    if sp.run(f'curl -sL https://downloads.rclone.org/rclone-current-linux-{arch}.zip -o /tmp/rclone.zip && unzip -qjo /tmp/rclone.zip "*/rclone" -d {bd} && chmod +x {bd}/rclone', shell=True).returncode == 0:
        print(f"✓ Installed"); return f'{bd}/rclone'
    return None
def cloud_login():
    rc = get_rclone() or cloud_install()
    if not rc: print("✗ rclone install failed"); return False
    sp.run([rc, 'config', 'create', RCLONE_REMOTE, 'drive'])
    if cloud_configured(): print(f"✓ Logged in as {cloud_account() or 'unknown'}"); cloud_sync(wait=True); return True
    print("✗ Login failed - try again"); return False
def cloud_logout():
    if cloud_configured(): sp.run([get_rclone(), 'config', 'delete', RCLONE_REMOTE]); print("✓ Logged out"); return True
    print("Not logged in"); return False
def cloud_status():
    if cloud_configured(): print(f"✓ Logged in: {cloud_account() or RCLONE_REMOTE}"); return True
    print("✗ Not logged in. Run: aio gdrive login"); return False

# Worktrees
def _wt_items(wt_dir): return sorted([d for d in os.listdir(wt_dir) if os.path.isdir(os.path.join(wt_dir, d))]) if os.path.exists(wt_dir) else []
def wt_list(wt_dir): items = _wt_items(wt_dir); print("Worktrees:" if items else "No worktrees"); [print(f"  {i}. {d}") for i, d in enumerate(items)]; return items
def wt_find(wt_dir, p): items = _wt_items(wt_dir); return os.path.join(wt_dir, items[int(p)]) if p.isdigit() and 0 <= int(p) < len(items) else next((os.path.join(wt_dir, i) for i in items if p in i), None)
def wt_create(proj, name, wt_dir):
    os.makedirs(wt_dir, exist_ok=True); wt = os.path.join(wt_dir, f"{os.path.basename(proj)}-{name}")
    r = _git(proj, 'worktree', 'add', '-b', f"wt-{os.path.basename(proj)}-{name}", wt, 'HEAD')
    return (print(f"✓ {wt}"), wt)[1] if r.returncode == 0 else (print(f"x {r.stderr.strip()}"), None)[1]
def wt_rm(p, proj_list, confirm=True):
    if not os.path.exists(p): print(f"x Not found: {p}"); return False
    proj = next((x for x in proj_list if os.path.basename(p).startswith(os.path.basename(x) + '-')), proj_list[0] if proj_list else None)
    if confirm and input(f"Remove {os.path.basename(p)}? (y/n): ").lower() not in ['y', 'yes']: return False
    _git(proj, 'worktree', 'remove', '--force', p); _git(proj, 'branch', '-D', f"wt-{os.path.basename(p)}")
    os.path.exists(p) and shutil.rmtree(p); print(f"✓ Removed {os.path.basename(p)}"); return True

# Session helpers
def _clip():
    if os.environ.get('TERMUX_VERSION'): return 'termux-clipboard-set'
    if sys.platform == 'darwin': return 'pbcopy'
    for c in ['wl-copy', 'xclip -selection clipboard -i', 'xsel --clipboard --input']:
        if shutil.which(c.split()[0]): return c
    return None

def _write_conf():
    l0 = '#[align=left][#S]#[align=centre]#{W:#[range=window|#{window_index}]#I:#W#{?window_active,*,}#[norange] }'
    sf = '#[range=user|sess]Ctrl+N:Win#[norange] #[range=user|new]Ctrl+T:New#[norange] #[range=user|close]Ctrl+W:Close#[norange] #[range=user|edit]Ctrl+E:Edit#[norange] #[range=user|kill]Ctrl+X:Kill#[norange] #[range=user|detach]Ctrl+Q:Quit#[norange]'
    sm = '#[range=user|sess]Sess#[norange] #[range=user|new]New#[norange] #[range=user|close]Close#[norange] #[range=user|edit]Edit#[norange] #[range=user|kill]Kill#[norange] #[range=user|detach]Quit#[norange]'
    l1 = '#{?#{e|<:#{client_width},70},' + sm + ',' + sf + '}'
    l2 = '#[align=left]#[range=user|esc]Esc#[norange]#[align=centre]#[range=user|kbd]Keyboard#[norange]'
    cc = _clip()
    conf = f'''# aio-managed-config
set -ga update-environment "WAYLAND_DISPLAY"
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
set -g status-format[0] "{l0}"
set -g status-format[1] "#[align=centre]{l1}"
set -g status-format[2] "{l2}"
bind-key -n C-n new-window
bind-key -n C-t split-window
bind-key -n C-w kill-pane
bind-key -n C-q detach
bind-key -n C-x confirm-before -p "Kill session? (y/n)" kill-session
bind-key -n C-e split-window "nvim ."
bind-key -T root MouseDown1Status if -F '#{{==:#{{mouse_status_range}},window}}' {{ select-window }} {{ run-shell 'r="#{{mouse_status_range}}"; case "$r" in sess) tmux new-window;; new) tmux split-window;; close) tmux kill-pane;; edit) tmux split-window nvim;; kill) tmux confirm-before -p "Kill?" kill-session;; detach) tmux detach;; esc) tmux send-keys Escape;; kbd) tmux set -g mouse off; tmux display-message "Tap terminal - mouse restores in 3s"; (sleep 3; tmux set -g mouse on) &;; esac' }}
'''
    if cc: conf += f'set -s copy-command "{cc}"\nbind -T copy-mode MouseDragEnd1Pane send -X copy-pipe-and-cancel\nbind -T copy-mode-vi MouseDragEnd1Pane send -X copy-pipe-and-cancel\n'
    if tm.ver >= '3.6': conf += 'set -g pane-scrollbars on\nset -g pane-scrollbars-position right\n'
    os.makedirs(_AIO_DIR, exist_ok=True)
    with open(_AIO_CONF, 'w') as f: f.write(conf)
    uc = Path(_USER_CONF).read_text() if os.path.exists(_USER_CONF) else ''
    if _SRC_LINE not in uc and '~/.aios/tmux.conf' not in uc:
        with open(_USER_CONF, 'a') as f: f.write(f'\n{_SRC_LINE}\n')
    return True

def ensure_tmux(cfg):
    if cfg.get('tmux_conf') != 'y' or not _write_conf(): return
    if sp.run(['tmux', 'info'], stdout=sp.DEVNULL, stderr=sp.DEVNULL).returncode != 0: return
    r = sp.run(['tmux', 'source-file', _AIO_CONF], capture_output=True, text=True)
    r.returncode != 0 and print(f"! tmux config error: {r.stderr.strip()}")
    sp.run(['tmux', 'refresh-client', '-S'], capture_output=True)

def _start_log(sn, parent=None):
    os.makedirs(LOG_DIR, exist_ok=True); lf = os.path.join(LOG_DIR, f"{DEVICE_ID}__{sn}.log")
    sp.run(['tmux', 'pipe-pane', '-t', sn, f"cat >> {lf}"], capture_output=True)
    with db() as c: c.execute("INSERT OR REPLACE INTO agent_logs VALUES (?,?,?,?)", (sn, parent, time.time(), DEVICE_ID))

def create_sess(sn, wd, cmd, cfg, env=None):
    ai = cmd and any(a in cmd for a in ['codex', 'claude', 'gemini', 'aider'])
    if ai: cmd = f'while :; do {cmd}; e=$?; [ $e -eq 0 ] && break; echo -e "\\n! Crashed (exit $e). [R]estart / [Q]uit: "; read -n1 k; [[ $k =~ [Rr] ]] || break; done'
    r = tm.new(sn, wd, cmd or '', env); ensure_tmux(cfg)
    if ai: sp.run(['tmux', 'split-window', '-v', '-t', sn, '-c', wd, 'sh -c "ls;exec $SHELL"'], capture_output=True); sp.run(['tmux', 'select-pane', '-t', sn, '-U'], capture_output=True)
    _start_log(sn)
    return r

def is_active(sn, thr=10):
    r = sp.run(['tmux', 'display-message', '-p', '-t', sn, '#{window_activity}'], capture_output=True, text=True)
    if r.returncode != 0: return False
    try: return int(time.time()) - int(r.stdout.strip()) < thr
    except: return False

def get_prefix(agent, cfg, wd=None):
    dp = cfg.get('default_prompt', '')
    pre = cfg.get('claude_prefix', 'Ultrathink. ') if 'claude' in agent else ''
    af = Path(wd or os.getcwd()) / 'AGENTS.md'
    return (dp + ' ' if dp else '') + pre + (af.read_text().strip() + ' ' if af.exists() else '')

def send_prefix(sn, agent, wd, cfg):
    pre = get_prefix(agent, cfg, wd)
    if not pre: return
    script = f'import time,subprocess as s\nfor _ in range(30):\n time.sleep(0.5);r=s.run(["tmux","capture-pane","-t","{sn}","-p","-S","-50"],capture_output=True,text=True);o=r.stdout.lower()\n if r.returncode!=0 or any(x in o for x in["context","claude","opus","gemini","codex"]):break\ns.run(["tmux","send-keys","-l","-t","{sn}",{repr(pre)}])'
    sp.Popen([sys.executable, '-c', script], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

def send_to_sess(sn, prompt, wait=False, timeout=None, enter=True):
    if not tm.has(sn): print(f"x Session {sn} not found"); return False
    tm.send(sn, prompt)
    if enter: time.sleep(0.1); tm.send(sn, '\n'); print(f"✓ Sent to '{sn}'")
    else: print(f"✓ Inserted into '{sn}'")
    if wait:
        print("Waiting...", end='', flush=True); start, last = time.time(), time.time()
        while True:
            if timeout and (time.time() - start) > timeout: print(f"\n! Timeout"); return True
            if is_active(sn, thr=2): last = time.time(); print(".", end='', flush=True)
            elif (time.time() - last) > 3: print("\n+ Done"); return True
            time.sleep(0.5)
    return True

def get_dir_sess(key, td, sess):
    if key not in sess: return None
    bn, _ = sess[key]; r = tm.ls()
    if r.returncode == 0:
        for s in [x for x in r.stdout.strip().split('\n') if x]:
            if not (s == bn or s.startswith(bn + '-')): continue
            pr = sp.run(['tmux', 'display-message', '-p', '-t', s, '#{pane_dead}:#{pane_current_path}'], capture_output=True, text=True)
            if pr.returncode == 0 and pr.stdout.strip().startswith('0:') and pr.stdout.strip()[2:] == td: return s
    sn, i = f"{bn}-{os.path.basename(td)}", 0
    while tm.has(sn if i == 0 else f"{sn}-{i}"): i += 1
    return sn if i == 0 else f"{sn}-{i}"

# Ghost sessions
def _ghost_spawn(dp, sm_map, cfg):
    if not os.path.isdir(dp) or not shutil.which('tmux'): return
    sf = os.path.join(DATA_DIR, 'ghost_state.json')
    try:
        with open(sf) as f: st = json.load(f)
        if time.time() - st.get('time', 0) > _GT: [sp.run(['tmux', 'kill-session', '-t', f'{_GP}{k}'], capture_output=True) for k in 'clg']
    except: pass
    for k in 'clg':
        g = f'{_GP}{k}'
        if tm.has(g):
            r = sp.run(['tmux', 'display-message', '-p', '-t', g, '#{pane_current_path}'], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip() == dp: continue
            sp.run(['tmux', 'kill-session', '-t', g], capture_output=True)
        _, cmd = sm_map.get(k, (None, None))
        if cmd: create_sess(g, dp, cmd, cfg); send_prefix(g, {'c': 'codex', 'l': 'claude', 'g': 'gemini'}[k], dp, cfg)
    try: Path(sf).write_text(json.dumps({'dir': dp, 'time': time.time()}))
    except: pass

def _ghost_claim(ak, td):
    g = f'{_GP}{_GM.get(ak, ak)}'
    if not tm.has(g): return None
    r = sp.run(['tmux', 'display-message', '-p', '-t', g, '#{pane_current_path}'], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != td: sp.run(['tmux', 'kill-session', '-t', g], capture_output=True); return None
    return g

# Terminal helpers
def detect_term(): return next((t for t in ['ptyxis', 'gnome-terminal', 'alacritty'] if shutil.which(t)), None)
_TA = {'ptyxis': ['ptyxis', '--'], 'gnome-terminal': ['gnome-terminal', '--'], 'alacritty': ['alacritty', '-e']}
def launch_win(sn, term=None):
    term = term or detect_term()
    if not term: print("x No terminal"); return False
    try: sp.Popen(_TA.get(term, []) + tm.attach(sn)); print(f"✓ {term}: {sn}"); return True
    except Exception as e: print(f"x {e}"); return False
def launch_dir(d, term=None):
    term, d = term or detect_term(), os.path.abspath(os.path.expanduser(d))
    if not term: print("x No terminal"); return False
    if not os.path.exists(d): print(f"x Not found: {d}"); return False
    cmds = {'ptyxis': ['ptyxis', '--working-directory', d], 'gnome-terminal': ['gnome-terminal', f'--working-directory={d}'], 'alacritty': ['alacritty', '--working-directory', d]}
    try: sp.Popen(cmds.get(term, [])); print(f"✓ {term}: {d}"); return True
    except Exception as e: print(f"x {e}"); return False

# Sync - JSONL append-only event log (git auto-merges text, never loses data)
def emit_event(table, op, data, device=None):
    """Append event to events.jsonl. Events are immutable - archive instead of delete."""
    import hashlib; eid = hashlib.md5(f"{time.time()}{os.getpid()}".encode()).hexdigest()[:8]
    event = {"ts": time.time(), "id": eid, "dev": device or DEVICE_ID, "op": f"{table}.{op}", "d": data}
    with open(EVENTS_PATH, "a") as f: f.write(json.dumps(event) + "\n")
    return eid

def replay_events(tables=None):
    """Rebuild state from events.jsonl. Tables: ssh, hub_jobs, notes."""
    if not os.path.exists(EVENTS_PATH): return
    state = {}; tables = tables or ['ssh', 'hub_jobs', 'notes']
    for line in open(EVENTS_PATH):
        try: e = json.loads(line)
        except: continue
        t, op = e["op"].split("."); d = e["d"]
        if t not in tables: continue
        if t not in state: state[t] = {}
        if op == "add": state[t][d.get("name") or d.get("id") or e["id"]] = {**d, "_ts": e["ts"], "_id": e["id"]}
        elif op == "update": k = d.get("name") or d.get("id"); state[t].get(k, {}).update({**d, "_ts": e["ts"]})
        elif op == "archive": k = d.get("name") or d.get("id"); k in state[t] and state[t][k].update({"_archived": e["ts"]})
        elif op == "rename" and d.get("old") in state.get(t, {}): state[t][d["old"]]["_archived"] = e["ts"]; state[t][d["new"]] = {**{k:v for k,v in state[t][d["old"]].items() if not k.startswith("_")}, "name": d["new"], "_ts": e["ts"], "_id": e["id"]}
    # Apply to db
    c = sqlite3.connect(DB_PATH)
    for t, items in state.items():
        active = {k: v for k, v in items.items() if not v.get("_archived")}
        if t == "ssh": c.execute("DELETE FROM ssh"); [c.execute("INSERT OR REPLACE INTO ssh(name,host)VALUES(?,?)", (v["name"], v.get("host",""))) for v in active.values()]
        elif t == "hub_jobs": pass  # hub_jobs has device column, handled separately
    c.commit(); c.close()

def db_sync(pull=False):
    if not os.path.isdir(f"{DATA_DIR}/.git") and not (shutil.which('gh') and (u:=sp.run(['gh','repo','view','aio-sync','--json','url','-q','.url'],capture_output=True,text=True).stdout.strip() or sp.run(['gh','repo','create','aio-sync','--private','-y'],capture_output=True,text=True).stdout.strip()) and sp.run(f'cd "{DATA_DIR}"&&git init -b main -q;git remote add origin {u} 2>/dev/null;git fetch origin 2>/dev/null&&git reset --hard origin/main 2>/dev/null||(git add -A&&git commit -m init -q&&git push -u origin main 2>/dev/null)',shell=True,capture_output=True) and os.path.isdir(f"{DATA_DIR}/.git")): return True
    c = sqlite3.connect(DB_PATH); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); my = (c.execute("SELECT path,display_order FROM projects WHERE device=?", (DEVICE_ID,)).fetchall(), c.execute("SELECT name,command,display_order FROM apps WHERE device=?", (DEVICE_ID,)).fetchall()); c.close()
    # Git merge with -X theirs: events.jsonl auto-merges (append-only), conflicts take remote (rebuild from events)
    pull and sp.run(f'cd "{DATA_DIR}" && git stash -q 2>/dev/null; git fetch -q && git merge -X theirs origin/main --no-edit -q; git stash pop -q 2>/dev/null', shell=True, capture_output=True)
    sp.run(f'cd "{DATA_DIR}" && git add -A && git diff --cached --quiet || git -c user.name=aio -c user.email=a@a commit -m sync -q && git push origin HEAD:main -q 2>/dev/null', shell=True, capture_output=True)
    pull and replay_events(['ssh'])  # Rebuild from merged events
    c = sqlite3.connect(DB_PATH); [c.execute("DELETE FROM "+t+" WHERE device=?", (DEVICE_ID,)) for t in ['projects','apps']]; [c.execute("INSERT INTO projects(path,display_order,device)VALUES(?,?,?)",(*p,DEVICE_ID)) for p in my[0]]; [c.execute("INSERT INTO apps(name,command,display_order,device)VALUES(?,?,?,?)",(*a,DEVICE_ID)) for a in my[1]]; c.commit(); c.close(); return True

def auto_backup():
    if not hasattr(os, 'fork'): return
    ts = os.path.join(DATA_DIR, ".backup_timestamp")
    if os.path.exists(ts) and time.time() - os.path.getmtime(ts) < 600: return
    if os.fork() == 0:
        bp = os.path.join(DATA_DIR, f"aio_auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"); sqlite3.connect(DB_PATH).backup(sqlite3.connect(bp))
        db_sync(); Path(ts).touch(); os._exit(0)

# Prompt toolkit
_prompt_toolkit = None
def _get_pt():
    global _prompt_toolkit
    if _prompt_toolkit is None:
        try:
            from prompt_toolkit import Application
            from prompt_toolkit.layout import Layout
            from prompt_toolkit.widgets import TextArea, Frame
            from prompt_toolkit.key_binding import KeyBindings
            _prompt_toolkit = {'A': Application, 'L': Layout, 'T': TextArea, 'F': Frame, 'K': KeyBindings}
        except: _prompt_toolkit = False
    return _prompt_toolkit if _prompt_toolkit else None

def input_box(prefill="", title="Ctrl+D to run, Ctrl+C to cancel"):
    pt = _get_pt()
    if not sys.stdin.isatty() or 'TMUX' in os.environ or not pt:
        print(f"[{title}] " if not prefill else f"[{title}]\n{prefill}\n> ", end="", flush=True)
        try: return input() if not prefill else prefill
        except: print("\nCancelled"); return None
    kb, cancelled = pt['K'](), [False]
    @kb.add('c-d')
    def _(e): e.app.exit()
    @kb.add('c-c')
    def _(e): cancelled[0] = True; e.app.exit()
    ta = pt['T'](text=prefill, multiline=True, focus_on_click=True)
    pt['A'](layout=pt['L'](pt['F'](ta, title=title)), key_bindings=kb, full_screen=True, mouse_support=True).run()
    return None if cancelled[0] else ta.text

# Update checking
def check_updates():
    ts = os.path.join(DATA_DIR, '.update_check')
    if os.path.exists(ts) and time.time() - os.path.getmtime(ts) < 1800: return
    if not hasattr(os, 'fork') or os.fork() != 0: return
    try: Path(ts).touch(); r = _sg('fetch', '--dry-run', timeout=5); r.returncode == 0 and r.stderr.strip() and Path(os.path.join(DATA_DIR, '.update_available')).touch()
    except: pass
    os._exit(0)

def show_update():
    m = os.path.join(DATA_DIR, '.update_available')
    if os.path.exists(m):
        if 'behind' in _sg('status', '-uno').stdout: print("! Update available! Run 'aio update'")
        else: os.path.exists(m) and os.remove(m)

# Help text
HELP_SHORT = """aio c|co|g|a    Start claude/codex/gemini/aider
aio <#>         Open project by number
aio prompt      Manage default prompt
aio help        All commands"""

HELP_FULL = """aio - AI agent session manager

AGENTS          c=claude  co=codex  g=gemini  a=aider
  aio <key>           Start agent in current dir
  aio <key> <#>       Start agent in project #
  aio <key>++         Start agent in new worktree

PROJECTS
  aio <#>             cd to project #
  aio add             Add current dir as project
  aio remove <#>      Remove project
  aio move <#> <#>    Reorder project
  aio scan            Add your repos fast

GIT
  aio push [msg]      Commit and push
  aio pull            Sync with remote
  aio diff            Show changes
  aio revert          Select commit to revert to

REMOTE
  aio ssh             List hosts
  aio ssh <#>         Connect to host
  aio run <#> "task"  Run task on remote

OTHER
  aio jobs            Active sessions
  aio ls              List tmux sessions
  aio attach          Reconnect to session
  aio kill            Kill all sessions
  aio n "text"        Quick note
  aio log             View agent logs
  aio config          View/set settings
  aio update          Update aio
  aio mono            Generate monolith for reading

EXPERIMENTAL
  aio agent "task"    Spawn autonomous subagent
  aio hub             Scheduled jobs (systemd)
  aio all             Multi-agent parallel runs
  aio tree            Create git worktree
  aio gdrive          Cloud sync (Google Drive)"""

def list_all(cache=True, quiet=False):
    p, a = load_proj(), load_apps(); Path(os.path.join(DATA_DIR, 'projects.txt')).write_text('\n'.join(p) + '\n')
    out = ([f"PROJECTS:"] + [f"  {i}. {'+' if os.path.exists(x) else 'x'} {x}" for i, x in enumerate(p)] if p else [])
    out += ([f"COMMANDS:"] + [f"  {len(p)+i}. {n} -> {fmt_cmd(c)}" for i, (n, c) in enumerate(a)] if a else [])
    txt = '\n'.join(out); not quiet and out and print(txt); cache and Path(os.path.join(DATA_DIR, 'help_cache.txt')).write_text(HELP_SHORT + '\n' + txt + '\n')
    return p, a

def parse_specs(argv, si, cfg):
    specs, parts, parsing = [], [], True
    for a in argv[si:]:
        if a in ['--seq', '--sequential']: continue
        if parsing and ':' in a and len(a) <= 4:
            p = a.split(':')
            if len(p) == 2 and p[0] in ['c', 'l', 'g'] and p[1].isdigit(): specs.append((p[0], int(p[1]))); continue
        parsing = False; parts.append(a)
    return (specs, cfg.get('codex_prompt', ''), True) if not parts else (specs, ' '.join(parts), False)
