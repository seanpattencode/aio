#!/usr/bin/env python3
# aio - AI agent session manager (merged with cloud sync)
import sys, os
# Fast-path for 'aio n <text>' - uses __import__('shutil').which('gh') not shell 'which' (missing on Arch etc)
if len(sys.argv) > 2 and sys.argv[1] in ('note', 'n'):
    import sqlite3, subprocess as sp; dd = os.path.expanduser("~/.local/share/aios"); db = f"{dd}/aio.db"; os.makedirs(dd, exist_ok=True); os.path.exists(db) and sqlite3.connect(db).execute("PRAGMA wal_checkpoint(TRUNCATE)").connection.close(); (os.path.isdir(f"{dd}/.git") or __import__('shutil').which('gh') and (u:=sp.run(['gh','repo','view','aio-sync','--json','url','-q','.url'],capture_output=True,text=True).stdout.strip() or sp.run(['gh','repo','create','aio-sync','--private','-y'],capture_output=True,text=True).stdout.strip()) and sp.run(f'cd "{dd}"&&git init -b main -q;git remote add origin {u} 2>/dev/null;git fetch origin 2>/dev/null&&git reset --hard origin/main 2>/dev/null||(git add -A&&git commit -m init -q&&git push -u origin main 2>/dev/null)',shell=True,capture_output=True)) and sp.run(f'cd "{dd}" && git fetch -q 2>/dev/null && git reset --hard origin/main 2>/dev/null', shell=True, capture_output=True); c = sqlite3.connect(db); c.execute("CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,t,s DEFAULT 0,d,c DEFAULT CURRENT_TIMESTAMP,proj)"); c.execute("INSERT INTO notes(t) VALUES(?)", (' '.join(sys.argv[2:]),)); c.commit(); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.close(); r = sp.run(f'cd "{dd}" && git add -A && git diff --cached --quiet || git -c user.name=aio -c user.email=a@a commit -m n && git push origin HEAD:main -q 2>&1', shell=True, capture_output=True, text=True) if os.path.isdir(f"{dd}/.git") else type('R',(),{'returncode':0})(); print("✓" if r.returncode == 0 else f"! {r.stderr.strip()[:40] or 'sync failed'}"); sys.exit(0)
import subprocess as sp, json, sqlite3, shlex, shutil, time, atexit, re, socket
from datetime import datetime
from pathlib import Path
DEVICE_ID = (sp.run(['getprop','ro.product.model'],capture_output=True,text=True).stdout.strip().replace(' ','-') or socket.gethostname()) if os.path.exists('/data/data/com.termux') else socket.gethostname()

_START, _CMD = time.time(), ' '.join(sys.argv[1:3]) if len(sys.argv) > 1 else 'help'
def _save_timing():
    try: d = os.path.expanduser("~/.local/share/aios"); os.makedirs(d, exist_ok=True); open(f"{d}/timing.jsonl", "a").write(json.dumps({"cmd": _CMD, "ms": int((time.time() - _START) * 1000), "ts": datetime.now().isoformat()}) + "\n")
    except: pass
atexit.register(_save_timing)

# Helpers
def _git(path, *a, **k): return sp.run(['git', '-C', path] + list(a), capture_output=True, text=True, **k)
def _tmux(*a): return sp.run(['tmux'] + list(a), capture_output=True, text=True)
def _ok(m): print(f"✓ {m}")
def _err(m): print(f"x {m}")
def _die(m, c=1): _err(m); sys.exit(c)
def _confirm(m): return input(f"{m} (y/n): ").strip().lower() in ['y', 'yes']
def _up(h): return not (lambda s,hp: s.settimeout(0.5) or s.connect_ex((hp[0].split('@')[-1], int(hp[1]) if len(hp)>1 else 22)))(socket.socket(), h.rsplit(':',1))  # only on add, not list (avoids port scan look)

_pexpect, _prompt_toolkit = None, None
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

# Paths
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROMPTS_DIR = Path(SCRIPT_DIR) / 'data' / 'prompts'
DATA_DIR = os.path.expanduser("~/.local/share/aios")
DB_PATH = os.path.join(DATA_DIR, "aio.db")
NOTE_DIR = os.path.join(DATA_DIR, "notebook")
LOG_DIR = os.path.join(DATA_DIR, "logs")
_GP, _GT = '_aio_ghost_', 300
_GM = {'c': 'l', 'l': 'l', 'g': 'g', 'o': 'l', 'co': 'c', 'cp': 'c', 'lp': 'l', 'gp': 'g'}
_AIO_DIR = os.path.expanduser('~/.aios')
_AIO_CONF = os.path.join(_AIO_DIR, 'tmux.conf')
_USER_CONF = os.path.expanduser('~/.tmux.conf')
_SRC_LINE = 'source-file ~/.aios/tmux.conf  # aio'
RCLONE_REMOTE, RCLONE_BACKUP_PATH = 'aio-gdrive', 'aio-backup'

# Git helpers
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

# Update
def _sg(*a, **k): return sp.run(['git', '-C', SCRIPT_DIR] + list(a), capture_output=True, text=True, **k)
def manual_update():
    if _sg('rev-parse', '--git-dir').returncode != 0: print("x Not in git repo"); return False
    print("Checking..."); before = _sg('rev-parse', 'HEAD').stdout.strip()[:8]
    if not before or _sg('fetch').returncode != 0: return False
    if 'behind' not in _sg('status', '-uno').stdout: print(f"✓ Up to date ({before})"); list_all(); return True
    print("Downloading..."); _sg('pull', '--ff-only')
    after = _sg('rev-parse', 'HEAD'); print(f"✓ {before} -> {after.stdout.strip()[:8]}" if after.returncode == 0 else "✓ Done")
    list_all(); print("Run: source ~/.bashrc"); return True

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

# Database - all data syncs to central sqlite via github (aio-sync repo). gdrive/rclone are backups only.
def db(): c = sqlite3.connect(DB_PATH); c.execute("PRAGMA journal_mode=WAL;"); return c

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with db() as c:
        # Core tables
        c.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, display_order INTEGER NOT NULL, device TEXT DEFAULT '*')")
        c.execute("CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, command TEXT NOT NULL, display_order INTEGER NOT NULL, device TEXT DEFAULT '*')")
        for t in ['projects', 'apps']:
            if 'device' not in [r[1] for r in c.execute(f"PRAGMA table_info({t})")]: c.execute(f"ALTER TABLE {t} ADD COLUMN device TEXT DEFAULT '*'")
        c.execute("CREATE TABLE IF NOT EXISTS sessions (key TEXT PRIMARY KEY, name TEXT NOT NULL, command_template TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS multi_runs (id TEXT PRIMARY KEY, repo TEXT NOT NULL, prompt TEXT NOT NULL, agents TEXT NOT NULL, status TEXT DEFAULT 'running', created_at TEXT DEFAULT CURRENT_TIMESTAMP, review_rank TEXT)")
        # Notes (merged from notebook/notes.db)
        c.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, t TEXT, s INTEGER DEFAULT 0, d TEXT, c TEXT DEFAULT CURRENT_TIMESTAMP, proj TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS note_projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, c TEXT DEFAULT CURRENT_TIMESTAMP)")
        # Todos/Jobs (merged from data/aios.db)
        c.execute("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, real_deadline INTEGER NOT NULL, virtual_deadline INTEGER, created_at INTEGER NOT NULL, completed_at INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS jobs (name TEXT PRIMARY KEY, step TEXT NOT NULL, status TEXT NOT NULL, path TEXT, session TEXT, updated_at INTEGER NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS hub_jobs (id INTEGER PRIMARY KEY, name TEXT, schedule TEXT, prompt TEXT, agent TEXT DEFAULT 'l', project TEXT, device TEXT, enabled INTEGER DEFAULT 1, last_run TEXT, parallel INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS agent_logs (session TEXT PRIMARY KEY, parent TEXT, started REAL, device TEXT)")
        if 'device' not in [r[1] for r in c.execute("PRAGMA table_info(agent_logs)")]: c.execute("ALTER TABLE agent_logs ADD COLUMN device TEXT")
        # Defaults
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

def get_prompt(name, show=False):
    pf = PROMPTS_DIR / f'{name}.txt'
    if pf.exists():
        show and print(f"Prompt: {pf}")
        return pf.read_text().strip()
    return None

def load_proj():
    with db() as c: return [r[0] for r in c.execute("SELECT path FROM projects WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,)).fetchall()]

def add_proj(p):
    p = os.path.abspath(os.path.expanduser(p))
    if not os.path.isdir(p): return False, f"Not a directory: {p}"
    with db() as c:
        if c.execute("SELECT 1 FROM projects WHERE path=? AND device IN (?, '*')", (p, DEVICE_ID)).fetchone(): return False, f"Exists: {p}"
        m = c.execute("SELECT MAX(display_order) FROM projects").fetchone()[0]
        c.execute("INSERT INTO projects (path, display_order, device) VALUES (?, ?, ?)", (p, 0 if m is None else m+1, DEVICE_ID)); c.commit()
    return True, f"Added: {p}"

def rm_proj(i):
    with db() as c:
        rows = c.execute("SELECT id, path FROM projects WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,)).fetchall()
        if i < 0 or i >= len(rows): return False, f"Invalid index: {i}"
        c.execute("DELETE FROM projects WHERE id=?", (rows[i][0],))
        for j, r in enumerate(c.execute("SELECT id FROM projects WHERE device=? ORDER BY display_order", (DEVICE_ID,))): c.execute("UPDATE projects SET display_order=? WHERE id=?", (j, r[0]))
        c.commit()
    return True, f"Removed: {rows[i][1]}"

def load_apps():
    with db() as c: return [(r[0], r[1]) for r in c.execute("SELECT name, command FROM apps WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,))]

def add_app(n, cmd):
    if not n or not cmd: return False, "Name and command required"
    with db() as c:
        if c.execute("SELECT 1 FROM apps WHERE name=? AND device IN (?, '*')", (n, DEVICE_ID)).fetchone(): return False, f"Exists: {n}"
        m = c.execute("SELECT MAX(display_order) FROM apps").fetchone()[0]
        c.execute("INSERT INTO apps (name, command, display_order, device) VALUES (?, ?, ?, ?)", (n, cmd, 0 if m is None else m+1, DEVICE_ID)); c.commit()
    return True, f"Added: {n}"

def rm_app(i):
    with db() as c:
        rows = c.execute("SELECT id, name FROM apps WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,)).fetchall()
        if i < 0 or i >= len(rows): return False, f"Invalid index: {i}"
        c.execute("DELETE FROM apps WHERE id=?", (rows[i][0],))
        for j, r in enumerate(c.execute("SELECT id FROM apps WHERE device=? ORDER BY display_order", (DEVICE_ID,))): c.execute("UPDATE apps SET display_order=? WHERE id=?", (j, r[0]))
        c.commit()
    return True, f"Removed: {rows[i][1]}"

def load_sess(cfg):
    with db() as c: data = c.execute("SELECT key, name, command_template FROM sessions").fetchall()
    dp, s = get_prompt('default'), {}
    esc = lambda p: cfg.get(p, dp).replace('\n', '\\n').replace('"', '\\"')
    for k, n, t in data:
        s[k] = (n, t.replace(' "{CLAUDE_PROMPT}"', '').replace(' "{CODEX_PROMPT}"', '').replace(' "{GEMINI_PROMPT}"', '') if k in ['cp','lp','gp'] else t.format(CLAUDE_PROMPT=esc('claude_prompt'), CODEX_PROMPT=esc('codex_prompt'), GEMINI_PROMPT=esc('gemini_prompt')))
    return s

# Cloud sync (merged from aioCloud.py)
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

# Stage 3 init
_s3 = False
cfg, PROJ, APPS, sess = {}, [], [], {}
CLAUDE_PREFIX, WORK_DIR, WT_DIR = 'Ultrathink. ', None, None

def _init3(skip=False):
    global _s3, cfg, PROJ, APPS, sess, CLAUDE_PREFIX, WORK_DIR, WT_DIR
    if _s3: return
    _s3 = True
    init_db(); cfg = load_cfg()
    CLAUDE_PREFIX = cfg.get('claude_prefix', 'Ultrathink. ')
    try: WORK_DIR = os.getcwd()
    except FileNotFoundError: WORK_DIR = os.path.expanduser("~"); os.chdir(WORK_DIR); print(f"! CWD invalid, using: {WORK_DIR}")
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/aiosWorktrees"))
    PROJ, APPS, sess = load_proj(), load_apps(), load_sess(cfg)
    if not skip:
        miss = [c for c in ['tmux', 'claude'] if not shutil.which(c)]
        miss and print(f"! Missing: {', '.join(miss)}. Run: aio install") and sys.exit(1)
    try: check_updates()
    except: pass

# Tmux config
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

def ensure_tmux():
    if cfg.get('tmux_conf') != 'y' or not _write_conf(): return
    if sp.run(['tmux', 'info'], stdout=sp.DEVNULL, stderr=sp.DEVNULL).returncode != 0: return
    r = sp.run(['tmux', 'source-file', _AIO_CONF], capture_output=True, text=True)
    r.returncode != 0 and print(f"! tmux config error: {r.stderr.strip()}")
    sp.run(['tmux', 'refresh-client', '-S'], capture_output=True)

def _start_log(sn, parent=None):
    os.makedirs(LOG_DIR, exist_ok=True); lf = os.path.join(LOG_DIR, f"{DEVICE_ID}__{sn}.log")
    sp.run(['tmux', 'pipe-pane', '-t', sn, f"cat >> {lf}"], capture_output=True)
    with db() as c: c.execute("INSERT OR REPLACE INTO agent_logs VALUES (?,?,?,?)", (sn, parent, time.time(), DEVICE_ID))

def create_sess(sn, wd, cmd, env=None):
    ai = cmd and any(a in cmd for a in ['codex', 'claude', 'gemini', 'aider'])
    if ai: cmd = f'while :; do {cmd}; e=$?; [ $e -eq 0 ] && break; echo -e "\\n! Crashed (exit $e). [R]estart / [Q]uit: "; read -n1 k; [[ $k =~ [Rr] ]] || break; done'
    r = tm.new(sn, wd, cmd or '', env); ensure_tmux()
    if ai: sp.run(['tmux', 'split-window', '-v', '-t', sn, '-c', wd, 'sh -c "ls;exec $SHELL"'], capture_output=True); sp.run(['tmux', 'select-pane', '-t', sn, '-U'], capture_output=True)
    _start_log(sn)
    return r

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

def is_active(sn, thr=10):
    r = sp.run(['tmux', 'display-message', '-p', '-t', sn, '#{window_activity}'], capture_output=True, text=True)
    if r.returncode != 0: return False
    try: return int(time.time()) - int(r.stdout.strip()) < thr
    except: return False

# Worktrees
def _wt_items(): return sorted([d for d in os.listdir(WT_DIR) if os.path.isdir(os.path.join(WT_DIR, d))]) if os.path.exists(WT_DIR) else []
def wt_list(): items = _wt_items(); print("Worktrees:" if items else "No worktrees"); [print(f"  {i}. {d}") for i, d in enumerate(items)]; return items
def wt_find(p): items = _wt_items(); return os.path.join(WT_DIR, items[int(p)]) if p.isdigit() and 0 <= int(p) < len(items) else next((os.path.join(WT_DIR, i) for i in items if p in i), None)
def wt_create(proj, name):
    os.makedirs(WT_DIR, exist_ok=True); wt = os.path.join(WT_DIR, f"{os.path.basename(proj)}-{name}")
    r = _git(proj, 'worktree', 'add', '-b', f"wt-{os.path.basename(proj)}-{name}", wt, 'HEAD')
    return (print(f"✓ {wt}"), wt)[1] if r.returncode == 0 else (print(f"x {r.stderr.strip()}"), None)[1]
def wt_rm(p, confirm=True):
    if not os.path.exists(p): print(f"x Not found: {p}"); return False
    proj = next((x for x in PROJ if os.path.basename(p).startswith(os.path.basename(x) + '-')), PROJ[0] if PROJ else None)
    if confirm and input(f"Remove {os.path.basename(p)}? (y/n): ").lower() not in ['y', 'yes']: return False
    _git(proj, 'worktree', 'remove', '--force', p); _git(proj, 'branch', '-D', f"wt-{os.path.basename(p)}")
    os.path.exists(p) and shutil.rmtree(p); print(f"✓ Removed {os.path.basename(p)}"); return True

def get_prefix(agent, wd=None):
    dp = cfg.get('default_prompt', '')
    pre = cfg.get('claude_prefix', 'Ultrathink. ') if 'claude' in agent else ''
    af = Path(wd or os.getcwd()) / 'AGENTS.md'
    return (dp + ' ' if dp else '') + pre + (af.read_text().strip() + ' ' if af.exists() else '')

def send_prefix(sn, agent, wd):
    pre = get_prefix(agent, wd)
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
            if is_active(sn, threshold=2): last = time.time(); print(".", end='', flush=True)
            elif (time.time() - last) > 3: print("\n+ Done"); return True
            time.sleep(0.5)
    return True

def get_dir_sess(key, td):
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
def _ghost_spawn(dp, sm_map):
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
        if cmd: create_sess(g, dp, cmd); send_prefix(g, {'c': 'codex', 'l': 'claude', 'g': 'gemini'}[k], dp)
    try: Path(sf).write_text(json.dumps({'dir': dp, 'time': time.time()}))
    except: pass

def _ghost_claim(ak, td):
    g = f'{_GP}{_GM.get(ak, ak)}'
    if not tm.has(g): return None
    r = sp.run(['tmux', 'display-message', '-p', '-t', g, '#{pane_current_path}'], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != td: sp.run(['tmux', 'kill-session', '-t', g], capture_output=True); return None
    return g

# Jobs
def list_jobs(running=False):
    r = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True)
    jbp = {}
    for s in (r.stdout.strip().split('\n') if r.returncode == 0 else []):
        if s and (pr := sp.run(['tmux', 'display-message', '-p', '-t', s, '#{pane_current_path}'], capture_output=True, text=True)).returncode == 0:
            jbp.setdefault(pr.stdout.strip(), []).append(s)
    for wp in [os.path.join(WT_DIR, d) for d in (os.listdir(WT_DIR) if os.path.exists(WT_DIR) else []) if os.path.isdir(os.path.join(WT_DIR, d))]:
        if wp not in jbp: jbp[wp] = []
    if not jbp: print("No jobs found"); return
    jobs = []
    for jp, ss in list(jbp.items()):
        if not os.path.exists(jp): [sp.run(['tmux', 'kill-session', '-t', s], capture_output=True) for s in ss]; continue
        active = any(is_active(s) for s in ss) if ss else False
        if running and not active: continue
        m = re.search(r'-(\d{8})-(\d{6})-', os.path.basename(jp))
        ct = datetime.strptime(f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S") if m else None
        td = (datetime.now() - ct).total_seconds() if ct else 0
        ctd = f"{int(td/60)}m ago" if td < 3600 else f"{int(td/3600)}h ago" if td < 86400 else f"{int(td/86400)}d ago" if ct else ""
        jobs.append({'p': jp, 'n': os.path.basename(jp), 's': ss, 'wt': jp.startswith(WT_DIR), 'a': active, 'ct': ct, 'ctd': ctd})
    print("Jobs:\n")
    for j in sorted(jobs, key=lambda x: x['ct'] or datetime.min):
        ctd = f" ({j['ctd']})" if j['ctd'] else ''
        print(f"  {'RUNNING' if j['a'] else 'REVIEW'}  {j['n']}{' [worktree]' if j['wt'] else ''}{ctd}")
        print(f"           aio {j['p'].replace(os.path.expanduser('~'), '~')}")
        for s in j['s']: print(f"           tmux attach -t {s}")
        print()

def parse_specs(argv, si):
    specs, parts, parsing = [], [], True
    for a in argv[si:]:
        if a in ['--seq', '--sequential']: continue
        if parsing and ':' in a and len(a) <= 4:
            p = a.split(':')
            if len(p) == 2 and p[0] in ['c', 'l', 'g'] and p[1].isdigit(): specs.append((p[0], int(p[1]))); continue
        parsing = False; parts.append(a)
    return (specs, cfg.get('codex_prompt', ''), True) if not parts else (specs, ' '.join(parts), False)

def fmt_cmd(c, mx=60):
    d = c.replace(os.path.expanduser('~'), '~')
    return d[:mx-3] + "..." if len(d) > mx else d

def list_all(cache=True, quiet=False):
    p, a = load_proj(), load_apps(); Path(os.path.join(DATA_DIR, 'projects.txt')).write_text('\n'.join(p) + '\n')
    out = ([f"PROJECTS:"] + [f"  {i}. {'+' if os.path.exists(x) else 'x'} {x}" for i, x in enumerate(p)] if p else [])
    out += ([f"COMMANDS:"] + [f"  {len(p)+i}. {n} -> {fmt_cmd(c)}" for i, (n, c) in enumerate(a)] if a else [])
    txt = '\n'.join(out); not quiet and out and print(txt); cache and Path(os.path.join(DATA_DIR, 'help_cache.txt')).write_text(HELP_SHORT + '\n' + txt + '\n')
    return p, a

def db_sync(pull=False):
    if not os.path.isdir(f"{DATA_DIR}/.git") and not (shutil.which('gh') and (u:=sp.run(['gh','repo','view','aio-sync','--json','url','-q','.url'],capture_output=True,text=True).stdout.strip() or sp.run(['gh','repo','create','aio-sync','--private','-y'],capture_output=True,text=True).stdout.strip()) and sp.run(f'cd "{DATA_DIR}"&&git init -b main -q;git remote add origin {u} 2>/dev/null;git fetch origin 2>/dev/null&&git reset --hard origin/main 2>/dev/null||(git add -A&&git commit -m init -q&&git push -u origin main 2>/dev/null)',shell=True,capture_output=True) and os.path.isdir(f"{DATA_DIR}/.git")): return True
    c = sqlite3.connect(DB_PATH); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); my = (c.execute("SELECT path,display_order FROM projects WHERE device=?", (DEVICE_ID,)).fetchall(), c.execute("SELECT name,command,display_order FROM apps WHERE device=?", (DEVICE_ID,)).fetchall()); c.close()
    pull and sp.run(f'cd "{DATA_DIR}" && git fetch -q && git reset --hard origin/main', shell=True, capture_output=True); sp.run(f'cd "{DATA_DIR}" && git add -A && git diff --cached --quiet || git -c user.name=aio -c user.email=a@a commit -m sync -q && git push origin HEAD:main -q 2>/dev/null', shell=True, capture_output=True)
    c = sqlite3.connect(DB_PATH); [c.execute("DELETE FROM "+t+" WHERE device=?", (DEVICE_ID,)) for t in ['projects','apps']]; [c.execute("INSERT INTO projects(path,display_order,device)VALUES(?,?,?)",(*p,DEVICE_ID)) for p in my[0]]; [c.execute("INSERT INTO apps(name,command,display_order,device)VALUES(?,?,?,?)",(*a,DEVICE_ID)) for a in my[1]]; c.commit(); c.close(); return True

def cmd_backup():
    if wda == 'setup':
        url = sys.argv[3] if len(sys.argv) > 3 else (sp.run(['gh', 'repo', 'view', 'aio-sync', '--json', 'url', '-q', '.url'], capture_output=True, text=True).stdout.strip() or sp.run(['gh', 'repo', 'create', 'aio-sync', '--private', '-y'], capture_output=True, text=True).stdout.strip()) if shutil.which('gh') else None
        if not url: _die("x No URL (need gh CLI or provide URL)")
        sp.run(f'cd "{DATA_DIR}" && git init -q 2>/dev/null; git remote set-url origin {url} 2>/dev/null || git remote add origin {url}; git fetch origin 2>/dev/null && git reset --hard origin/main 2>/dev/null || (git add -A && git commit -m "init" -q && git push -u origin main)', shell=True); print("✓ Sync ready"); return
    gu = sp.run(f'cd "{DATA_DIR}" && git remote get-url origin 2>/dev/null', shell=True, capture_output=True, text=True).stdout.strip(); print(f"Git: {'✓ '+gu if gu else 'x (aio backup setup)'}")

def auto_backup():
    if not hasattr(os, 'fork'): return
    ts = os.path.join(DATA_DIR, ".backup_timestamp")
    if os.path.exists(ts) and time.time() - os.path.getmtime(ts) < 600: return
    if os.fork() == 0:
        bp = os.path.join(DATA_DIR, f"aio_auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"); sqlite3.connect(DB_PATH).backup(sqlite3.connect(bp))
        db_sync(); Path(ts).touch(); os._exit(0)

# MAIN
arg = sys.argv[1] if len(sys.argv) > 1 else None
_S2_MAX = 50
_s2_ms = int((time.time() - _START) * 1000)
if _s2_ms > _S2_MAX: print(f"! PERF ERROR: Stage 2 took {_s2_ms}ms (max {_S2_MAX}ms)"); sys.exit(1)
_init3(skip=(arg in ('install', 'deps')))
show_update()
wda = sys.argv[2] if len(sys.argv) > 2 else None
new_win = '--new-window' in sys.argv or '-w' in sys.argv
with_term = '--with-terminal' in sys.argv or '-t' in sys.argv
if new_win: sys.argv = [a for a in sys.argv if a not in ['--new-window', '-w']]; arg = sys.argv[1] if len(sys.argv) > 1 else None; wda = sys.argv[2] if len(sys.argv) > 2 else None
if with_term: sys.argv = [a for a in sys.argv if a not in ['--with-terminal', '-t']]; arg = sys.argv[1] if len(sys.argv) > 1 else None; wda = sys.argv[2] if len(sys.argv) > 2 else None; new_win = True

dir_only = new_win and arg and not arg.startswith('+') and not arg.endswith('--') and not arg.startswith('w') and arg not in sess
if dir_only: wda, arg = arg, None

is_wda_prompt = False
_cmd_kw = {'add', 'remove', 'rm', 'cmd', 'command', 'commands', 'app', 'apps', 'prompt', 'a', 'all', 'review', 'w'}
if wda and wda.isdigit() and arg not in _cmd_kw:
    idx = int(wda)
    if 0 <= idx < len(PROJ): wd = PROJ[idx]
    elif 0 <= idx - len(PROJ) < len(APPS):
        an, ac = APPS[idx - len(PROJ)]
        print(f"> Running: {an}\n   Command: {ac}")
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash'), '-c', ac])
    else: wd = WORK_DIR
elif wda and os.path.isdir(os.path.expanduser(wda)): wd = wda
elif wda: is_wda_prompt = True; wd = WORK_DIR
else: wd = WORK_DIR

# Project number shortcut
if arg and arg.isdigit() and not wda:
    idx = int(arg)
    if 0 <= idx < len(PROJ):
        print(f"Opening project {idx}: {PROJ[idx]}")
        sp.Popen([sys.executable, __file__, '_ghost', PROJ[idx]], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        os.chdir(PROJ[idx]); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    elif 0 <= idx - len(PROJ) < len(APPS):
        an, ac = APPS[idx - len(PROJ)]
        print(f"> Running: {an}\n   Command: {fmt_cmd(ac)}")
        os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash'), '-c', ac])
    else: print(f"x Invalid index: {idx}"); sys.exit(1)

# Worktree commands
if arg and arg.startswith('w') and arg not in ('watch', 'web') and not os.path.isfile(arg):
    if arg == 'w': wt_list(); sys.exit(0)
    wp = wt_find(arg[1:].rstrip('-'))
    if arg.endswith('-'): wt_rm(wp, confirm='--yes' not in sys.argv and '-y' not in sys.argv) if wp else print(f"x Not found"); sys.exit(0)
    if wp: os.chdir(wp); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])
    print(f"x Not found: {arg[1:]}"); sys.exit(1)

if new_win and not arg: launch_dir(wd); sys.exit(0)
if arg == '_ghost':
    if len(sys.argv) > 2: _init3(); _ghost_spawn(sys.argv[2], sess)
    sys.exit(0)

# Help
HELP_SHORT = """aio c|co|g|a    Start claude/codex/gemini/aider
aio <#>         Open project by number
aio prompt      Manage default prompt
aio help        All commands"""

HELP_FULL = f"""aio - AI agent session manager

AGENTS          c=claude  co=codex  g=gemini  a=aider
  aio <key>           Start agent in current dir
  aio <key> <#>       Start agent in project #
  aio <key>++         Start agent in new worktree

PROJECTS
  aio <#>             cd to project #
  aio add             Add current dir as project
  aio remove <#>      Remove project
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

EXPERIMENTAL
  aio agent "task"    Spawn autonomous subagent
  aio hub             Scheduled jobs (systemd)
  aio all             Multi-agent parallel runs
  aio tree            Create git worktree
  aio gdrive          Cloud sync (Google Drive)"""

# Commands
def cmd_help(): print(HELP_SHORT); list_all()
def cmd_help_full(): print(HELP_FULL); list_all()
def cmd_update(): manual_update()
def cmd_jobs(): list_jobs(running='--running' in sys.argv or '-r' in sys.argv)
def cmd_kill(): input("Kill all tmux sessions? (y/n): ").lower() in ['y', 'yes'] and (print("✓ Killed all tmux"), sp.run(['tmux', 'kill-server']))

def cmd_attach():
    cwd = os.getcwd()
    def _a(s): os.execvp('tmux', ['tmux', 'switch-client' if 'TMUX' in os.environ else 'attach', '-t', s])
    if WT_DIR in cwd:
        p = cwd.replace(WT_DIR + '/', '').split('/')
        if len(p) >= 2 and tm.has(s := f"{p[0]}-{p[1]}"): _a(s)
    with db() as c: runs = c.execute("SELECT id, repo FROM multi_runs ORDER BY created_at DESC LIMIT 10").fetchall()
    if runs:
        for i, (rid, repo) in enumerate(runs): print(f"{i}. {'●' if tm.has(f'{os.path.basename(repo)}-{rid}') else '○'} {os.path.basename(repo)}-{rid}")
        ch = input("Select #: ").strip()
        if ch.isdigit() and int(ch) < len(runs): _a(f"{os.path.basename(runs[int(ch)][1])}-{runs[int(ch)][0]}")
    print("No session")

def cmd_cleanup():
    wts = _wt_items()
    with db() as c: cnt = c.execute("SELECT COUNT(*) FROM multi_runs").fetchone()[0]
    if not wts and not cnt: print("Nothing to clean"); sys.exit(0)
    print(f"Will delete: {len(wts)} dirs, {cnt} db entries")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").lower() in ['y', 'yes']) or _die("x")
    for wt in wts:
        try: shutil.rmtree(os.path.join(WT_DIR, wt)); print(f"✓ {wt}")
        except: pass
    [_git(p, 'worktree', 'prune') for p in PROJ if os.path.exists(p)]
    with db() as c: c.execute("DELETE FROM multi_runs"); c.commit()
    print("✓ Cleaned")

def cmd_config():
    global cfg
    key, val = wda, ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else None
    if not key: [print(f"  {k}: {v[:50]}{'...' if len(v)>50 else ''}") for k, v in sorted(cfg.items())]
    elif val:
        val = '' if val in ('off', 'none', '""', "''") else val
        with db() as c: c.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (key, val)); c.commit()
        cfg = load_cfg(); list_all(quiet=True)
        print(f"✓ {key}={'(cleared)' if not val else val}")
    else: print(f"{key}: {cfg.get(key, '(not set)')}")

def cmd_ls():
    r = sp.run(['tmux', 'list-sessions', '-F', '#{session_name}'], capture_output=True, text=True)
    if r.returncode != 0: print("No tmux sessions found"); sys.exit(0)
    sl = [s for s in r.stdout.strip().split('\n') if s]
    if not sl: print("No tmux sessions found"); sys.exit(0)
    print("Tmux Sessions:\n")
    for s in sl:
        pr = sp.run(['tmux', 'display-message', '-p', '-t', s, '#{pane_current_path}'], capture_output=True, text=True)
        print(f"  {s}: {pr.stdout.strip() if pr.returncode == 0 else ''}")

def cmd_diff():
    sp.run(['git', 'fetch', 'origin'], capture_output=True); cwd = os.getcwd()
    b = sp.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True).stdout.strip()
    target = 'origin/main' if b.startswith('wt-') else f'origin/{b}'
    diff = sp.run(['git', 'diff', target], capture_output=True, text=True).stdout
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
    ins = int(re.search(r'(\d+) insertion', stat).group(1)) if 'insertion' in stat else 0
    dels = int(re.search(r'(\d+) deletion', stat).group(1)) if 'deletion' in stat else 0
    stat and print(f"\n{stat} | Net: {'+' if ins-dels >= 0 else ''}{ins-dels} lines")

def cmd_send():
    wda or _die("Usage: aio send <session> <prompt> [--wait] [--no-enter]")
    prompt = ' '.join(a for a in sys.argv[3:] if a not in ('--wait', '--no-enter'))
    prompt or _die("No prompt provided")
    send_to_sess(wda, prompt, wait='--wait' in sys.argv, timeout=60, enter='--no-enter' not in sys.argv) or sys.exit(1)

def cmd_watch():
    wda or _die("Usage: aio watch <session> [duration]")
    dur = int(sys.argv[3]) if len(sys.argv) > 3 else None
    print(f"Watching '{wda}'" + (f" for {dur}s" if dur else " (once)"))
    patterns = {re.compile(p): r for p, r in [(r'Are you sure\?', 'y'), (r'Continue\?', 'yes'), (r'\[y/N\]', 'y'), (r'\[Y/n\]', 'y')]}
    last, start = "", time.time()
    while True:
        if dur and (time.time() - start) > dur: break
        r = sp.run(['tmux', 'capture-pane', '-t', wda, '-p'], capture_output=True, text=True)
        if r.returncode != 0: print(f"x Session {wda} not found"); sys.exit(1)
        if r.stdout != last:
            for p, resp in patterns.items():
                if p.search(r.stdout): sp.run(['tmux', 'send-keys', '-t', wda, resp, 'Enter']); print(f"✓ Auto-responded"); break
            last = r.stdout
        time.sleep(0.1)

def cmd_push():
    cwd, skip = os.getcwd(), '--yes' in sys.argv or '-y' in sys.argv
    if _git(cwd, 'rev-parse', '--git-dir').returncode != 0:
        _git(cwd, 'init', '-b', 'main'); Path(os.path.join(cwd, '.gitignore')).touch(); _git(cwd, 'add', '-A'); _git(cwd, 'commit', '-m', 'Initial commit'); print("✓ Initialized")
        if not shutil.which('gh') or sp.run(['gh', 'auth', 'status'], capture_output=True).returncode != 0:
            print("! gh not installed or not authenticated. Run: brew install gh && gh auth login"); return
        u = sys.argv[2] if len(sys.argv) > 2 and '://' in sys.argv[2] else ('' if skip else input(f"Create '{os.path.basename(cwd)}' on GitHub? (y=public/p=private): ").strip())
        if u in 'y p yes private'.split() and sp.run(['gh', 'repo', 'create', os.path.basename(cwd), '--private' if 'p' in u else '--public', '--source', '.', '--push'], timeout=60).returncode == 0: print("✓ Pushed"); return
        if u and '://' in u: _git(cwd, 'remote', 'add', 'origin', u)
    ensure_git_cfg(); r = _git(cwd, 'rev-parse', '--git-dir'); is_wt = '.git/worktrees/' in r.stdout.strip() or cwd.startswith(WT_DIR)
    args = [a for a in sys.argv[2:] if a not in ['--yes', '-y'] and '://' not in a]
    target = args[0] if args and os.path.isfile(os.path.join(cwd, args[0])) else None
    if target: args = args[1:]
    msg = ' '.join(args) or (f"Update {target}" if target else f"Update {os.path.basename(cwd)}")
    env = _env()
    if is_wt:
        wn = os.path.basename(cwd)
        proj = next((p for p in PROJ if wn.startswith(os.path.basename(p) + '-')), None) or _die(f"x Could not find project for {wn}")
        wb = _git(cwd, 'branch', '--show-current').stdout.strip()
        print(f"Worktree: {wn} | Branch: {wb} | Msg: {msg}")
        to_main = skip or input("Push to: 1=main 2=branch [1]: ").strip() != '2'
        _git(cwd, 'add', target or '-A'); r = _git(cwd, 'commit', '-m', msg)
        r.returncode == 0 and print(f"✓ Committed: {msg}")
        if to_main:
            main = _git_main(proj); _git(proj, 'fetch', 'origin', env=env)
            ahead = _git(proj, 'rev-list', '--count', f'origin/{main}..{main}').stdout.strip()
            if ahead and int(ahead) > 0:
                ol = set(_git(cwd, 'diff', '--name-only', f'origin/{main}...HEAD').stdout.split()) & set(_git(proj, 'diff', '--name-only', f'origin/{main}..{main}').stdout.split()) - {''}
                m = f"[i] {main} {ahead} ahead (different files)\nMerge?" if not ol else f"! {main} {ahead} ahead, overlap: {', '.join(ol)}\n{_git(proj, 'log', f'origin/{main}..{main}', '--oneline').stdout.strip()}\nContinue?"
                skip or input(f"{m} (y/n): ").lower() in ['y', 'yes'] or _die("x Cancelled")
            _git(proj, 'checkout', main).returncode == 0 or _die(f"x Checkout {main} failed")
            _git(proj, 'merge', wb, '--no-edit', '-X', 'theirs').returncode == 0 or _die("x Merge failed")
            print(f"✓ Merged {wb} -> {main}"); _git_push(proj, main, env) or sys.exit(1)
            _git(proj, 'fetch', 'origin', env=env); _git(proj, 'reset', '--hard', f'origin/{main}')
            if not skip and input(f"\nDelete worktree '{wn}'? (y/n): ").strip().lower() in ['y', 'yes']:
                _git(proj, 'worktree', 'remove', '--force', cwd); _git(proj, 'branch', '-D', f'wt-{wn}')
                os.path.exists(cwd) and shutil.rmtree(cwd); print("✓ Cleaned up worktree")
                os.chdir(proj); os.execvp(os.environ.get('SHELL', 'bash'), [os.environ.get('SHELL', 'bash')])
        else: _git(cwd, 'push', '-u', 'origin', wb, env=env) and print(f"✓ Pushed to {wb}")
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
    env = _env(); _git(cwd, 'fetch', 'origin', env=env)
    ref = 'origin/main' if _git(cwd, 'rev-parse', '--verify', 'origin/main').returncode == 0 else 'origin/master'
    info = _git(cwd, 'log', '-1', '--format=%h %s', ref).stdout.strip()
    print(f"! DELETE local changes -> {info}")
    ('--yes' in sys.argv or '-y' in sys.argv or input("Continue? (y/n): ").strip().lower() in ['y', 'yes']) or _die("x Cancelled")
    _git(cwd, 'reset', '--hard', ref); _git(cwd, 'clean', '-f', '-d'); print(f"✓ Synced: {info}")

def cmd_revert():
    cwd = os.getcwd(); _git(cwd, 'rev-parse', '--git-dir').returncode == 0 or _die("x Not a git repo")
    logs = _git(cwd, 'log', '--format=%h %ad %s', '--date=format:%m/%d %H:%M', '-15').stdout.strip().split('\n')
    for i, l in enumerate(logs): print(f"  {i}. {l}")
    c = input("\nRevert to #: ").strip()
    if not c.isdigit() or int(c) >= len(logs): _die("x Invalid")
    h = logs[int(c)].split()[0]
    r = _git(cwd, 'revert', '--no-commit', f'{h}..HEAD'); _git(cwd, 'commit', '-m', f'revert to {h}') if r.returncode == 0 else None
    print(f"✓ Reverted to {h}") if r.returncode == 0 else _die(f"x Failed: {r.stderr.strip()}")

def cmd_install():
    script = os.path.join(SCRIPT_DIR, "install.sh")
    if os.path.exists(script):
        os.execvp("bash", ["bash", script])
    else:
        url = "https://raw.githubusercontent.com/seanpattencode/aio/main/install.sh"
        os.execvp("bash", ["bash", "-c", f"curl -fsSL {url} | bash"])

def cmd_uninstall():
    if input("Uninstall aio? (y/n): ").lower() in ['y', 'yes']:
        import shutil; [os.remove(p) for p in [os.path.expanduser(f"~/.local/bin/{f}") for f in ["aio", "aioUI.py"]] if os.path.exists(p)]; shutil.rmtree(os.path.expanduser("~/.local/share/aios"), ignore_errors=True); print("✓ aio uninstalled"); os._exit(0)

def cmd_deps():
    _run = lambda c: sp.run(c, shell=True).returncode == 0
    sudo = '' if os.environ.get('TERMUX_VERSION') else 'sudo '
    for p, a in [('pexpect','python3-pexpect'),('prompt_toolkit','python3-prompt-toolkit')]:
        try: __import__(p); ok = True
        except: ok = _run(f'{sudo}apt-get install -y {a}') or _run(f'{sys.executable} -m pip install --user {p}')
        print(f"{'✓' if ok else 'x'} {p}")
    shutil.which('tmux') or _run(f'{sudo}apt-get install -y tmux') or _run('brew install tmux'); print(f"{'✓' if shutil.which('tmux') else 'x'} tmux")
    shutil.which('npm') or _run(f'{sudo}apt-get install -y nodejs npm') or _run('brew install node')
    nv = int(sp.run(['node','-v'],capture_output=True,text=True).stdout.strip().lstrip('v').split('.')[0]) if shutil.which('node') else 0
    nv < 25 and _run(f'{sudo}npm i -g n && {sudo}n latest'); print(f"{'✓' if shutil.which('node') else 'x'} node")
    for c, p in [('codex','@openai/codex'),('claude','@anthropic-ai/claude-code'),('gemini','@google/gemini-cli')]:
        shutil.which(c) or _run(f'{sudo}npm i -g {p}'); print(f"{'✓' if shutil.which(c) else 'x'} {c}")
    shutil.which('aider') or _run(f'{sys.executable} -m pip install --user aider-chat'); print(f"{'✓' if shutil.which('aider') else 'x'} aider")

def cmd_prompt():
    global cfg
    val = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    if not val:
        cur = cfg.get('default_prompt', '')
        print(f"Current: {cur or '(none)'}"); val = input("New (empty to clear): ").strip()
        if val == '' and cur == '': return
    val = '' if val in ('off', 'none', '""', "''") else val
    with db() as c: c.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", ('default_prompt', val)); c.commit()
    cfg = load_cfg(); list_all(quiet=True)
    print(f"✓ {'(cleared)' if not val else val}")

def cmd_gdrive():
    if wda == 'login': cloud_configured() and not _confirm("Already logged in. Switch?") or cloud_login()
    elif wda == 'logout': cloud_logout()
    elif wda == 'sync': cloud_sync(wait=True)
    elif wda == 'pull': cloud_pull_notes()
    else: cloud_status()

def cmd_note():
    db_sync(pull=True)
    raw = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    with db() as c:
        if raw: c.execute("INSERT INTO notes(t) VALUES(?)", (raw,)); c.commit(); db_sync(); print("✓"); sys.exit()
        projs = [r[0] for r in c.execute("SELECT name FROM note_projects ORDER BY c")]
        notes = c.execute("SELECT id,t,d,proj FROM notes WHERE s=0 ORDER BY c DESC").fetchall()
        if not notes: print("aio n <text>"); sys.exit()
        if not sys.stdin.isatty(): [print(f"{t}" + (f" @{p}" if p else "")) for _,t,_,p in notes[:10]]; sys.exit()
        print(f"{len(notes)} notes | [a]ck [e]dit [p]rojects [m]ore [q]uit | 1/20=due")
        for i,(nid,txt,due,proj) in enumerate(notes):
            print(f"\n[{i+1}/{len(notes)}] {txt}" + (f" @{proj}" if proj else "") + (f" [{due}]" if due else "")); ch = input("> ").strip().lower()
            if ch == 'a': c.execute("UPDATE notes SET s=1 WHERE id=?", (nid,)); c.commit(); db_sync(); print("✓")
            elif ch == 'e': nv = input("new: "); nv and (c.execute("UPDATE notes SET t=? WHERE id=?", (nv, nid)), c.commit(), db_sync(), print("✓"))
            elif '/' in ch: from dateutil.parser import parse; d=str(parse(ch,dayfirst=False))[:19].replace(' 00:00:00',''); c.execute("UPDATE notes SET d=? WHERE id=?", (d, nid)); c.commit(); db_sync(); print(f"✓ {d}")
            elif ch == 'm': print("\n=== Archive ==="); [print(f"  [{ct[:16]}] {t}" + (f" @{p}" if p else "")) for t,p,ct in c.execute("SELECT t,proj,c FROM notes WHERE s=1 ORDER BY c DESC LIMIT 20")]; input("[enter]")
            elif ch == 'p':
                while True:
                    print(("\n" + "\n".join(f"  {j}. {x}" for j,x in enumerate(projs))) if projs else "\n  (no projects)"); pc = input("p> ").strip()
                    if not pc: break
                    if pc[:3]=='rm ' and pc[3:].isdigit() and int(pc[3:])<len(projs): n=projs.pop(int(pc[3:])); c.execute("DELETE FROM note_projects WHERE name=?",(n,)); c.commit(); db_sync(); print(f"✓ {n}"); continue
                    if pc.isdigit() and int(pc) < len(projs):
                        pname = projs[int(pc)]
                        while True:
                            pnotes = c.execute("SELECT id,t,d FROM notes WHERE s=0 AND proj=? ORDER BY c DESC", (pname,)).fetchall(); print(f"\n=== {pname} === {len(pnotes)} notes"); [print(f"  {j}. {pt}" + (f" [{pd}]" if pd else "")) for j,(pid,pt,pd) in enumerate(pnotes)]; pn = input(f"{pname}> ").strip()
                            if not pn: break
                            c.execute("INSERT INTO notes(t,proj) VALUES(?,?)", (pn,pname)); c.commit(); db_sync(); print("✓")
                        break
                    c.execute("INSERT OR IGNORE INTO note_projects(name) VALUES(?)", (pc,)); c.commit(); projs.append(pc) if pc not in projs else None; db_sync(); print(f"✓ {pc}")
            elif ch == 'q': sys.exit()
            elif ch: c.execute("INSERT INTO notes(t) VALUES(?)", (ch,)); c.commit(); db_sync(); print("✓")

def cmd_add():
    args = [a for a in sys.argv[2:] if a != '--global']
    ig = '--global' in sys.argv[2:]
    if len(args) >= 2 and not os.path.isdir(os.path.expanduser(args[0])):
        interp = ['python', 'python3', 'node', 'npm', 'ruby', 'perl', 'java', 'go', 'sh', 'bash', 'npx']
        if args[0] in interp:
            cv = ' '.join(args); print(f"Command: {cv}")
            cn = input("Name for this command: ").strip()
            if not cn: print("x Cancelled"); sys.exit(1)
        else: cn, cv = args[0], ' '.join(args[1:])
        cwd, home = os.getcwd(), os.path.expanduser('~')
        if not ig and cwd != home and not cv.startswith('cd '): cv = f"cd {cwd.replace(home, '~')} && {cv}"
        ok, msg = add_app(cn, cv); print(f"{'✓' if ok else 'x'} {msg}")
        if ok: auto_backup(); list_all()
        sys.exit(0 if ok else 1)
    path = os.path.abspath(os.path.expanduser(args[0])) if args else os.getcwd()
    ok, msg = add_proj(path); print(f"{'✓' if ok else 'x'} {msg}")
    if ok: auto_backup(); list_all()
    sys.exit(0 if ok else 1)

def cmd_remove():
    if not wda: print("Usage: aio remove <#|name>\n"); list_all(); sys.exit(0)
    projs, apps = load_proj(), load_apps()
    if wda.isdigit():
        idx = int(wda)
        if idx < len(projs): ok, msg = rm_proj(idx)
        elif idx < len(projs) + len(apps): ok, msg = rm_app(idx - len(projs))
        else: print(f"x Invalid index: {idx}"); list_all(); sys.exit(1)
    else:
        ai = next((i for i, (n, _) in enumerate(apps) if n.lower() == wda.lower()), None)
        if ai is None: print(f"x Not found: {wda}"); list_all(); sys.exit(1)
        ok, msg = rm_app(ai)
    print(f"{'✓' if ok else 'x'} {msg}")
    if ok: auto_backup(); list_all()
    sys.exit(0 if ok else 1)

def cmd_dash():
    if not tm.has('dash'): sp.run(['tmux', 'new-session', '-d', '-s', 'dash', '-c', wd]); sp.run(['tmux', 'split-window', '-h', '-t', 'dash', '-c', wd, 'sh -c "aio jobs; exec $SHELL"'])
    os.execvp('tmux', ['tmux', 'switch-client' if 'TMUX' in os.environ else 'attach', '-t', 'dash'])

def cmd_multi():
    if wda == 'set':
        ns = ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else ''
        if not ns: print(f"Current: {load_cfg().get('multi_default', 'c:3')}"); sys.exit(0)
        if not parse_specs([''] + ns.split(), 1)[0]: _die(f"Invalid: {ns}")
        with db() as c: c.execute("INSERT OR REPLACE INTO config VALUES ('multi_default', ?)", (ns,)); c.commit(); print(f"✓ Default: {ns}"); sys.exit(0)
    pp, si = (PROJ[int(wda)], 3) if wda and wda.isdigit() and int(wda) < len(PROJ) else (os.getcwd(), 2)
    specs, _, _ = parse_specs(sys.argv, si)
    if not specs: ds = load_cfg().get('multi_default', 'l:3'); specs, _, _ = parse_specs([''] + ds.split(), 1); print(f"Using: {ds}")
    total, rn, rid = sum(c for _, c in specs), os.path.basename(pp), datetime.now().strftime('%Y%m%d-%H%M%S')
    sn, rd = f"{rn}-{rid}", os.path.join(WT_DIR, rn, rid)
    cd = os.path.join(rd, "candidates"); os.makedirs(cd, exist_ok=True)
    with open(os.path.join(rd, "run.json"), "w") as f: json.dump({"agents": [f"{k}:{c}" for k, c in specs], "created": rid, "repo": pp}, f)
    with db() as c: c.execute("INSERT OR REPLACE INTO multi_runs VALUES (?, ?, '', ?, 'running', CURRENT_TIMESTAMP, NULL)", (rid, pp, json.dumps([f"{k}:{c}" for k, c in specs]))); c.commit()
    print(f"{total} agents in {rn}/{rid}..."); env, launched, an = _env(), [], {}
    for ak, cnt in specs:
        bn, bc = sess.get(ak, (None, None))
        if not bn: continue
        for i in range(cnt):
            an[bn] = an.get(bn, 0) + 1; aid = f"{ak}{i}"; wt = os.path.join(cd, aid)
            sp.run(['git', '-C', pp, 'worktree', 'add', '-b', f'wt-{rn}-{rid}-{aid}', wt], capture_output=True, env=env)
            if os.path.exists(wt): launched.append((wt, bc)); print(f"✓ {bn}-{an[bn]}")
    if not launched: print("x No agents created"); sys.exit(1)
    sp.run(['tmux', 'new-session', '-d', '-s', sn, '-c', launched[0][0], launched[0][1]], env=env)
    for wt, bc in launched[1:]: sp.run(['tmux', 'split-window', '-h', '-t', sn, '-c', wt, bc], env=env)
    sp.run(['tmux', 'split-window', '-h', '-t', sn, '-c', cd], env=env); sp.run(['tmux', 'send-keys', '-t', sn, f'n={len(launched)}; while read -ep "> " c; do [ -n "$c" ] && for i in $(seq 0 $((n-1))); do tmux send-keys -l -t ":.$i" "$c"; tmux send-keys -t ":.$i" C-m; done; done', 'C-m'])
    sp.run(['tmux', 'select-layout', '-t', sn, 'even-horizontal'], env=env); ensure_tmux()
    print(f"\n+ '{sn}': {len(launched)}+broadcast"); print(f"   tmux switch-client -t {sn}") if "TMUX" in os.environ else os.execvp('tmux', ['tmux', 'attach', '-t', sn])

def cmd_tree():
    proj = PROJ[int(wda)] if wda and wda.isdigit() and int(wda) < len(PROJ) else os.getcwd()
    _git(proj, 'rev-parse', '--git-dir').returncode == 0 or _die("x Not a git repo")
    wp = wt_create(proj, datetime.now().strftime('%Y%m%d-%H%M%S'))
    wp or sys.exit(1)
    os.chdir(wp); os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash')])

def cmd_e():
    if 'TMUX' in os.environ: os.execvp('nvim', ['nvim', '.'])
    else: create_sess('edit', os.getcwd(), 'nvim .'); os.execvp('tmux', ['tmux', 'attach', '-t', 'edit'])

def cmd_x(): sp.run(['tmux', 'kill-server']); print("✓ All sessions killed")
def cmd_p(): list_all()
def cmd_web(): sp.Popen(['xdg-open', 'https://google.com/search?q='+'+'.join(sys.argv[2:]) if len(sys.argv)>2 else 'https://google.com'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
def cmd_copy():
    L=os.popen('tmux capture-pane -pJ -S -99').read().split('\n') if os.environ.get('TMUX') else []; P=[i for i,l in enumerate(L) if '$'in l and'@'in l]; u=next((i for i in reversed(P) if 'copy'in L[i]),len(L)); p=next((i for i in reversed(P) if i<u),-1); full='\n'.join(L[p+1:u]).strip() if P else ''; sp.run(_clip(),shell=True,input=full,text=True); s=full.replace('\n',' '); print(f"✓ {s[:23]+'...'+s[-24:] if len(s)>50 else s}")

def cmd_log():
    os.makedirs(LOG_DIR, exist_ok=True); db_sync(pull=True); logs = sorted(Path(LOG_DIR).glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
    total = sum(f.stat().st_size for f in logs); print(f"Logs: {len(logs)} files, {total/1024/1024:.1f}MB")
    if not logs: return
    if wda == 'clean': days = int(sys.argv[3]) if len(sys.argv) > 3 else 7; old = [f for f in logs if (time.time() - f.stat().st_mtime) > days*86400]; [f.unlink() for f in old]; print(f"✓ Deleted {len(old)} logs older than {days}d"); return
    if wda == 'tail': f = logs[int(sys.argv[3])] if len(sys.argv) > 3 and sys.argv[3].isdigit() else logs[0]; os.execvp('tail', ['tail', '-f', str(f)])
    print(f"  {'#':<3} {'date':<11} {'device':<10} {'session':<25} {'size':>6}")
    for i, f in enumerate(logs[:20]):
        sz, nm, mt = f.stat().st_size/1024, f.stem, f.stat().st_mtime; parts = nm.split('__'); dev, sn = (parts[0][:10], '__'.join(parts[1:])) if len(parts) > 1 else ('-', nm)
        print(f"  {i}. {datetime.fromtimestamp(mt).strftime('%m/%d %H:%M')}  {dev:<10} {sn:<25} {sz:>5.0f}KB")
    print(f"\naio log tail [#] | aio log clean [days]")
    if (c := input("> ").strip()).isdigit() and int(c) < len(logs): sp.run(['tmux', 'new-window', f'cat "{logs[int(c)]}"; read'])

def cmd_done():
    Path(f"{DATA_DIR}/.done").touch(); print("✓ done")

def cmd_agent():
    existing = [s.split(':')[0] for s in sp.run(['tmux', 'ls'], capture_output=True, text=True).stdout.split('\n') if s.startswith('agent-')]
    if wda and wda.startswith('agent-') and wda in existing:
        sn, task = wda, ' '.join(sys.argv[3:])
    elif wda and wda.isdigit() and int(wda) < len(existing):
        sn, task = existing[int(wda)], ' '.join(sys.argv[3:])
    else:
        agent = wda if wda in sess else 'g'; task = ' '.join(sys.argv[3:]) if wda in sess else ' '.join(sys.argv[2:])
        if not task:
            if existing: print("Active agents:"); [print(f"  {i}. {s}") for i,s in enumerate(existing)]
            _die("Usage: aio agent [g|c|l|#|name] <task>")
        sn = f"agent-{agent}-{int(time.time())}"; _, cmd = sess[agent]
        parent = sp.run(['tmux', 'display-message', '-p', '#S'], capture_output=True, text=True).stdout.strip(); parent = parent if parent.startswith('agent-') else None
        print(f"Agent: {agent} | Task: {task[:50]}..."); tm.new(sn, os.getcwd(), cmd); _start_log(sn, parent)
        print("Waiting for agent to start..."); last_out, stable = '', 0
        for _ in range(60):
            time.sleep(1); out = sp.run(['tmux', 'capture-pane', '-t', sn, '-p'], capture_output=True, text=True).stdout
            if 'Type your message' in out:
                if out == last_out: stable += 1
                else: stable = 0
                if stable >= 2: break
            last_out = out
    timeout, done_file = 300, Path(f"{DATA_DIR}/.done"); done_file.unlink(missing_ok=True)
    prompt = f'{task}\n\nCommands: "aio agent g <task>" spawns gemini subagent, "aio agent l <task>" spawns claude subagent. Subagents auto-signal when done. When YOUR task is fully complete, run: aio done'
    print(f"Sending to {sn}..."); tm.send(sn, prompt); time.sleep(0.3); sp.run(['tmux', 'send-keys', '-t', sn, 'Enter'])
    print("Waiting for completion..."); start = time.time()
    while not done_file.exists():
        if time.time() - start > timeout: print(f"x Timeout after {timeout}s"); break
        time.sleep(1)
    output = sp.run(['tmux', 'capture-pane', '-t', sn, '-p', '-S', '-100'], capture_output=True, text=True).stdout
    print(f"--- Output ---\n{output}\n--- End ---")

def cmd_wt_plus():
    key = arg[:-2]
    if key not in sess: print(f"x Unknown session key: {key}"); return
    proj = PROJ[int(wda)] if wda and wda.isdigit() and int(wda) < len(PROJ) else wd
    bn, cmd = sess[key]
    wp = wt_create(proj, f"{bn}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    if not wp: return
    sn = os.path.basename(wp); create_sess(sn, wp, cmd, env=_env())
    send_prefix(sn, bn, wp)
    if new_win: launch_win(sn)
    elif "TMUX" in os.environ: print(f"✓ Session: {sn}")
    else: os.execvp(tm.attach(sn)[0], tm.attach(sn))

def cmd_dir_file():
    if os.path.isdir(os.path.expanduser(arg)):
        d = os.path.expanduser('~' + arg) if arg.startswith('/projects/') else os.path.expanduser(arg)
        print(f"{d}", flush=True); sp.run(['ls', d])
    elif os.path.isfile(arg):
        ext = os.path.splitext(arg)[1].lower()
        if ext == '.py': os.execvp(sys.executable, [sys.executable, arg] + sys.argv[2:])
        elif ext in ('.html', '.htm'): __import__('webbrowser').open('file://' + os.path.abspath(arg))
        elif ext == '.md': os.execvp(os.environ.get('EDITOR', 'nvim'), [os.environ.get('EDITOR', 'nvim'), arg])

def cmd_sess():
    if 'TMUX' in os.environ and arg in sess and len(arg) == 1:
        an, cmd = sess[arg]; pid = sp.run(['tmux', 'split-window', '-bvP', '-F', '#{pane_id}', '-c', wd, cmd], capture_output=True, text=True).stdout.strip()
        pid and (sp.run(['tmux', 'split-window', '-v', '-t', pid, '-c', wd, 'sh -c "ls;exec $SHELL"']), sp.run(['tmux', 'select-pane', '-t', pid]))
        pid and send_prefix(pid, an, wd)
        sys.exit(0)
    if arg in _GM and not wda and (g := _ghost_claim(arg, wd)):
        sn = f"{sess[arg][0] if arg in sess else arg}-{os.path.basename(wd)}"; sp.run(['tmux', 'rename-session', '-t', g, sn], capture_output=True); print(f"Ghost: {sn}"); os.execvp('tmux', ['tmux', 'attach', '-t', sn])
    sn = get_dir_sess(arg, wd); env = _env(); created = False
    if sn is None: n, c = sess.get(arg, (arg, None)); create_sess(n, wd, c or arg, env=env); sn = n; created = True
    elif not tm.has(sn): create_sess(sn, wd, sess[arg][1], env=env); created = True
    else: _start_log(sn)
    is_p = arg.endswith('p') and not arg.endswith('pp') and len(arg) == 2 and arg in sess
    pp = [a for a in sys.argv[(2 if is_wda_prompt else (3 if wda else 2)):] if a not in ['-w', '--new-window', '--yes', '-y', '-t', '--with-terminal']]
    if pp: print("Prompt queued"); sp.Popen([sys.executable, __file__, 'send', sn, ' '.join(pp)] + (['--no-enter'] if is_p else []), stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif is_p and (pm := {'cp': cfg.get('codex_prompt', ''), 'lp': cfg.get('claude_prompt', ''), 'gp': cfg.get('gemini_prompt', '')}.get(arg)): sp.Popen([sys.executable, __file__, 'send', sn, pm, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif created and arg in sess: send_prefix(sn, sess[arg][0], wd)
    if new_win: launch_win(sn); with_term and launch_dir(wd)
    elif "TMUX" in os.environ or not sys.stdout.isatty(): print(f"✓ Session: {sn}")
    else: os.execvp(tm.attach(sn)[0], tm.attach(sn))

def cmd_set():
    f=sys.argv[2]if len(sys.argv)>2 else None;p=Path(DATA_DIR)/f if f else None;v=sys.argv[3]if len(sys.argv)>3 else None
    if not f:s="on"if(Path(DATA_DIR)/'n').exists()else"off";print(f"1. n [{s}] commands without aio prefix\n   aio set n {'off'if s=='on'else'on'}");return
    if v=='on':p.touch();print(f"✓ on - open new terminal tab")
    elif v=='off':p.unlink(missing_ok=True);print(f"✓ off - open new terminal tab")
    else:print("on"if p.exists()else"off")

def _sshd_running(): return sp.run(['pgrep', '-x', 'sshd'], capture_output=True).returncode == 0
def _sshd_ip(): r = sp.run("ifconfig 2>/dev/null | grep -A1 wlan0 | grep inet | awk '{print $2}'", shell=True, capture_output=True, text=True); return r.stdout.strip() or '?'
def _sshd_port(): return 8022 if os.environ.get('TERMUX_VERSION') else 22

def cmd_ssh():
    try: import keyring as kr
    except: kr = None
    _pw = lambda n,v=None: (kr.set_password('aio-ssh',n,v),v)[1] if v and kr else kr.get_password('aio-ssh',n) if kr else None
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS ssh(name TEXT PRIMARY KEY, host TEXT, pw TEXT)"); hosts = list(c.execute("SELECT name,host FROM ssh")); hmap = {r[0]: r[1] for r in hosts}
        [(c.execute("UPDATE ssh SET pw=NULL WHERE name=?",(n,)), _pw(n,p)) for n,_,p in c.execute("SELECT * FROM ssh WHERE pw IS NOT NULL")]; c.commit()
    if wda == 'start': r = sp.run(['sshd'], capture_output=True, text=True) if os.environ.get('TERMUX_VERSION') else sp.run(['sudo', '/usr/sbin/sshd'], capture_output=True, text=True); print(f"✓ sshd started (port {_sshd_port()})") if r.returncode == 0 or _sshd_running() else print(f"x sshd failed: {r.stderr.strip() or 'install openssh-server'}"); return
    if wda == 'stop': sp.run(['pkill', '-x', 'sshd']) if os.environ.get('TERMUX_VERSION') else sp.run(['sudo', 'pkill', '-x', 'sshd']); print("✓ sshd stopped" if not _sshd_running() else "x failed"); return
    if wda in ('status', 's'): u, ip, p = os.environ.get('USER', 'u0_a'), _sshd_ip(), _sshd_port(); print(f"{'✓ RUNNING' if _sshd_running() else 'x STOPPED'}  ssh {u}@{ip} -p {p}"); return
    if not wda: u, ip, p = os.environ.get('USER', 'u0_a'), _sshd_ip(), _sshd_port(); shutil.which('ssh') or print("! pkg install openssh"); print(f"SSH {'✓ ON' if _sshd_running() else 'x OFF'}  →  ssh {u}@{ip} -p {p}\n  start/stop/status  server control\n  setup              install & configure\n  add/rm <name>      manage hosts\nHosts:"); [print(f"  {i}. {n}: {h}{' [pw]' if _pw(n) else ''}") for i,(n,h) in enumerate(hosts)] or print("  (none)"); return
    if wda == 'setup': ip = _sshd_ip(); u = os.environ.get('USER', 'user'); ok = _sshd_running(); cmd = 'pkg install -y openssh && sshd' if os.environ.get('TERMUX_VERSION') else 'sudo apt install -y openssh-server && sudo systemctl enable --now ssh'; (not ok and input("SSH not running. Install? (y/n): ").lower() in ['y', 'yes'] and sp.run(cmd, shell=True)); ok = ok or _sshd_running(); print(f"This: {DEVICE_ID} ({u}@{ip}:{_sshd_port()})\nSSH: {'✓ running' if ok else 'x not running'}\n\nTo connect here from another device:\n  ssh {u}@{ip} -p {_sshd_port()}"); return
    if wda == 'key': kf = Path.home()/'.ssh/id_ed25519'; kf.exists() or sp.run(['ssh-keygen','-t','ed25519','-N','','-f',str(kf)]); print(f"Public key:\n{(kf.with_suffix('.pub')).read_text().strip()}"); return
    if wda == 'auth': d = Path.home()/'.ssh'; d.mkdir(exist_ok=True); af = d/'authorized_keys'; k = input("Paste public key: ").strip(); af.open('a').write(f"\n{k}\n"); af.chmod(0o600); print("✓ Added"); return
    if wda in ('info','i'): [print(f"{n}: ssh {'-p '+hp[1]+' ' if len(hp:=h.rsplit(':',1))>1 else ''}{hp[0]}") for n,h in hosts]; return
    if wda == 'rm' and len(sys.argv) > 3: n=sys.argv[3]; _pw(n) and kr and kr.delete_password('aio-ssh',n); (c:=db()).execute("DELETE FROM ssh WHERE name=?",(n,)); c.commit(); print(f"✓ rm {n}"); return
    if wda == 'add': h=re.sub(r'\s+-p\s*(\d+)',r':\1',input("Host (user@ip): ").strip()); _up(h) or _die(f"x cannot connect to {h}"); n=input("Name: ").strip() or h.split('@')[-1].split(':')[0].split('.')[-1]; pw=input("Password? ").strip() or None; pw and _pw(n,pw); (c:=db()).execute("INSERT OR REPLACE INTO ssh(name,host) VALUES(?,?)",(n,h)); c.commit(); print(f"✓ Added {n}={h}{' [pw]' if pw else ''}"); return
    nm = hosts[int(wda)][0] if wda.isdigit() and int(wda) < len(hosts) else (_die(f"x No host #{wda}. Run: aio ssh") if wda.isdigit() else wda); shutil.which('ssh') or _die("x ssh not installed"); h=hmap.get(nm,nm); pw=_pw(nm); hp=h.rsplit(':',1); cmd=['ssh','-tt','-o','StrictHostKeyChecking=accept-new']+(['-p',hp[1]] if len(hp)>1 else [])+[hp[0]]
    if 'cmd' in sys.argv or '--cmd' in sys.argv: print(' '.join(cmd)); return
    if not pw and nm in hmap: pw=input("Password? ").strip()
    pw and not shutil.which('sshpass') and _die("x need sshpass"); print(f"Connecting to {nm}...\n[AI: use 'timeout N aio ssh X' - interactive session needs TTY]", file=sys.stderr, flush=True); os.execvp('sshpass',['sshpass','-p',pw]+cmd) if pw else os.execvp('ssh',cmd)

def cmd_hub():
    _tx=os.path.exists('/data/data/com.termux');LOG=f"{DATA_DIR}/hub.log";db_sync(pull=True)
    if _tx:c=db();c.execute("UPDATE hub_jobs SET device=? WHERE device='localhost'",(DEVICE_ID,));c.commit();c.close();db_sync()
    _pt=lambda s:(lambda m:f"{int(m[1])+(12 if m[3]=='pm'and int(m[1])!=12 else(-int(m[1])if m[3]=='am'and int(m[1])==12 else 0))}:{m[2]}"if m else s)(re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)?$',s.lower().strip()))
    def _install(nm,sched,cmd):
        if _tx:
            shutil.which('crontab')or sp.run(['pkg','install','-y','cronie'],capture_output=True);sp.run(['pgrep','crond'],capture_output=True).returncode!=0 and sp.run(['crond'])
            h,m=sched.split(':');old='\n'.join(l for l in(sp.run(['crontab','-l'],capture_output=True,text=True).stdout or'').split('\n')if f'# aio:{nm}'not in l).strip()
            sp.run(['crontab','-'],input=f"{old}\n{m} {h} * * * {cmd} >> {LOG} 2>&1 # aio:{nm}\n",text=True)
        else:
            sd=Path.home()/'.config/systemd/user';sd.mkdir(parents=True,exist_ok=True)
            (sd/f'aio-{nm}.service').write_text(f"[Unit]\nDescription={nm}\n[Service]\nType=oneshot\nExecStart={cmd}\n")
            (sd/f'aio-{nm}.timer').write_text(f"[Unit]\nDescription={nm}\n[Timer]\nOnCalendar={sched}\nPersistent=true\n[Install]\nWantedBy=timers.target\n")
            [sp.run(['systemctl','--user']+a,capture_output=True)for a in[['daemon-reload'],['enable','--now',f'aio-{nm}.timer']]]
    def _uninstall(nm):
        if _tx:sp.run(['crontab','-'],input='\n'.join(l for l in(sp.run(['crontab','-l'],capture_output=True,text=True).stdout or'').split('\n')if f'# aio:{nm}'not in l)+'\n',text=True)
        else:sd=Path.home()/'.config/systemd/user';sp.run(['systemctl','--user','disable','--now',f'aio-{nm}.timer'],capture_output=True);[(sd/f'aio-{nm}.{x}').unlink(missing_ok=True)for x in['timer','service']]
    with db() as c:jobs=c.execute("SELECT id,name,schedule,prompt,device,enabled FROM hub_jobs ORDER BY device,name").fetchall()
    if not wda:
        print(f"{'#':<3}{'Name':<12}{'Time':<7}{'Device':<10}{'On':<4}{'Command'}");[print(f"{i:<3}{j[1]:<12}{j[2]:<7}{j[4]:<10}{'✓'if j[5]else'x':<4}{(j[3]or'')[:30]}")for i,j in enumerate(jobs)]or print("  (none)")
        while(c:=input("\nadd|rm <#>|run <#>|sync|log\n> ").strip()):sp.run([sys.executable,__file__,'hub']+c.split());jobs=db().execute("SELECT id,name,schedule,prompt,device,enabled FROM hub_jobs ORDER BY device,name").fetchall();print(f"{'#':<3}{'Name':<12}{'Time':<7}{'Device':<10}{'On':<4}{'Command'}");[print(f"{i:<3}{j[1]:<12}{j[2]:<7}{j[4]:<10}{'✓'if j[5]else'x':<4}{(j[3]or'')[:30]}")for i,j in enumerate(jobs)]or print("  (none)")
        return
    if wda=='add':
        a=sys.argv[3:]+['']*3;n,s,c=a[0],a[1],' '.join(a[2:]).strip()
        while not n:n=input("Name: ").strip().replace(' ','-')
        while':'not in s:s=input("Time (9:00am, 14:00): ").strip()
        s=_pt(s)
        if not c:items=[os.path.basename(p)for p in PROJ]+[nm for nm,_ in APPS];print("Commands:");[print(f"  {i}. {x}")for i,x in enumerate(items)];c=input("# or cmd: ").strip();c=f'aio {c}'if c.isdigit()and int(c)<len(items)else c
        with db() as cn:cn.execute("INSERT OR REPLACE INTO hub_jobs(name,schedule,prompt,device,enabled)VALUES(?,?,?,?,1)",(n,s,c,DEVICE_ID));cn.commit()
        cmd=c.replace('aio ',f'{sys.executable} {os.path.abspath(__file__)} ')if c.startswith('aio ')else c;_install(n,s,cmd);db_sync();print(f"✓ {n} @ {s}")
    elif wda=='sync':
        [_uninstall(j[1])for j in jobs];mine=[j for j in jobs if j[4]==DEVICE_ID and j[5]]
        for j in mine:cmd=j[3].replace('aio ',f'{sys.executable} {os.path.abspath(__file__)} ')if j[3].startswith('aio ')else j[3];_install(j[1],j[2],cmd)
        print(f"✓ synced {len(mine)} jobs")
    elif wda in('rm','run','log'):
        n=sys.argv[3]if len(sys.argv)>3 else'';j=jobs[int(n)]if n.isdigit()and int(n)<len(jobs)else next((x for x in jobs if x[1]==n),None)
        if not j:print(f"x {n}?");return
        if wda=='rm':_uninstall(j[1]);c=db();c.execute("DELETE FROM hub_jobs WHERE id=?",(j[0],));c.commit();c.close();db_sync();print(f"✓ rm {j[1]}")
        elif wda=='log':print(open(LOG).read()[-2000:]if os.path.exists(LOG)else'No logs')
        else:cmd=j[3].replace('aio ',f'{sys.executable} {os.path.abspath(__file__)} ')if j[3].startswith('aio ')else j[3];sp.run(cmd,shell=True);print(f"✓ {j[1]}")

def cmd_run():
    args = sys.argv[2:]; hosts = list(db().execute("SELECT name,host FROM ssh")); [print(f"  {i}. {n}") for i,(n,h) in enumerate(hosts)] if args and not args[0].isdigit() else None
    hi = int(args.pop(0)) if args and args[0].isdigit() else int(input("Host #: ").strip()); agent = args.pop(0) if args and args[0] in 'clg' else 'l'
    with db() as c: n,h = list(c.execute("SELECT name,host FROM ssh"))[hi]; hp = h.rsplit(':',1); import keyring; pw = keyring.get_password('aio-ssh',n); task = ' '.join(args); proj = os.path.basename(os.getcwd())
    cmd = f'cd ~/projects/{proj} && aio {agent}++' + (f' && sleep 2 && tmux send-keys -t $(tmux ls -F "#{{session_name}}" | grep "^{proj}" | tail -1) {shlex.quote(task)} Enter' if task else '')
    print(f"→ {n}"); os.execvp('sshpass', ['sshpass','-p',pw,'ssh','-tt','-p',hp[1] if len(hp)>1 else '22',hp[0],cmd])

def cmd_scan():
    args = sys.argv[2:]; gh_mode = 'gh' in args or 'github' in args; args = [a for a in args if a not in ('gh', 'github')]
    sel = next((a for a in args if a.isdigit() or a == 'all' or '-' in a and a.replace('-','').isdigit()), None)
    if gh_mode:
        r = sp.run(['gh', 'repo', 'list', '-L', '50', '--json', 'name,url'], capture_output=True, text=True); repos = json.loads(r.stdout) if r.returncode == 0 else []
        cloned = {os.path.basename(p) for p in load_proj()}; repos = [(r['name'], r['url']) for r in repos if r['name'] not in cloned]
        if not repos: print("No new GitHub repos"); return
        for i, (n, u) in enumerate(repos): print(f"  {i}. {n}")
        if not sel: sel = input("\nClone+add (#, #-#, 'all', or q): ").strip() if sys.stdin.isatty() else 'q'
        if sel in ('q', ''): return
        idxs = list(range(len(repos))) if sel == 'all' else [j for x in sel.replace(',', ' ').split() for j in (range(int(x.split('-')[0]), int(x.split('-')[1])+1) if '-' in x else [int(x)]) if 0 <= j < len(repos)]
        pd = os.path.expanduser('~/projects'); os.makedirs(pd, exist_ok=True)
        for i in idxs: n, u = repos[i]; dest = f"{pd}/{n}"; r = sp.run(['gh', 'repo', 'clone', u, dest], capture_output=True, text=True); ok, _ = add_proj(dest) if r.returncode == 0 or os.path.isdir(dest) else (False, ''); print(f"{'✓' if ok else 'x'} {n}")
    else:
        default = next((p for p in ['~/projects', '~/storage/shared', '~'] if os.path.isdir(os.path.expanduser(p))), '~')
        d = os.path.expanduser(next((a for a in args if a not in (sel,) and not a.startswith('-')), default)); existing = set(load_proj())
        repos = sorted([p.parent for p in Path(d).rglob('.git') if p.exists() and str(p.parent) not in existing and '/.cargo/' not in str(p) and '/lazy/' not in str(p) and '/aiosWorktrees/' not in str(p)], key=lambda x: x.name.lower())[:50]
        if not repos: print(f"No new repos in {d}"); return
        for i, r in enumerate(repos): print(f"  {i}. {r.name:<25} {str(r)}")
        if not sel: sel = input("\nAdd (#, #-#, 'all', or q): ").strip() if sys.stdin.isatty() else 'q'
        if sel in ('q', ''): return
        idxs = list(range(len(repos))) if sel == 'all' else [j for x in sel.replace(',', ' ').split() for j in (range(int(x.split('-')[0]), int(x.split('-')[1])+1) if '-' in x else [int(x)]) if 0 <= j < len(repos)]
        for i in idxs: ok, _ = add_proj(str(repos[i])); print(f"{'✓' if ok else 'x'} {repos[i].name}")
    auto_backup() if idxs else None

# Dispatch
CMDS = {
    None: cmd_help, '': cmd_help, 'help': cmd_help_full, 'hel': cmd_help_full, '--help': cmd_help_full, '-h': cmd_help_full,
    'update': cmd_update, 'upd': cmd_update, 'jobs': cmd_jobs, 'job': cmd_jobs, 'kill': cmd_kill, 'kil': cmd_kill, 'killall': cmd_kill, 'attach': cmd_attach, 'att': cmd_attach,
    'cleanup': cmd_cleanup, 'cle': cmd_cleanup, 'config': cmd_config, 'con': cmd_config, 'ls': cmd_ls, 'diff': cmd_diff, 'dif': cmd_diff, 'send': cmd_send, 'sen': cmd_send,
    'watch': cmd_watch, 'wat': cmd_watch, 'push': cmd_push, 'pus': cmd_push, 'pull': cmd_pull, 'pul': cmd_pull, 'revert': cmd_revert, 'rev': cmd_revert, 'set': cmd_set,
    'install': cmd_install, 'ins': cmd_install, 'uninstall': cmd_uninstall, 'uni': cmd_uninstall, 'deps': cmd_deps, 'dep': cmd_deps, 'prompt': cmd_prompt, 'pro': cmd_prompt, 'gdrive': cmd_gdrive, 'gdr': cmd_gdrive, 'note': cmd_note, 'n': cmd_note, 'settings': cmd_set,
    'add': cmd_add, 'remove': cmd_remove, 'rem': cmd_remove, 'rm': cmd_remove, 'dash': cmd_dash, 'das': cmd_dash, 'all': cmd_multi, 'backup': cmd_backup, 'bak': cmd_backup, 'scan': cmd_scan, 'sca': cmd_scan,
    'e': cmd_e, 'x': cmd_x, 'p': cmd_p, 'copy': cmd_copy, 'cop': cmd_copy, 'log': cmd_log, 'done': cmd_done, 'agent': cmd_agent, 'tree': cmd_tree, 'tre': cmd_tree, 'dir': lambda: (print(f"{os.getcwd()}"), sp.run(['ls'])), 'web': cmd_web, 'ssh': cmd_ssh,
    'run': cmd_run,
    'hub': cmd_hub,
}

if arg in CMDS: CMDS[arg]()
elif arg and arg.endswith('++') and not arg.startswith('w'): cmd_wt_plus()
elif arg and (os.path.isdir(os.path.expanduser(arg)) or os.path.isfile(arg) or (arg.startswith('/projects/') and os.path.isdir(os.path.expanduser('~' + arg)))): cmd_dir_file()
elif arg in sess or (arg and len(arg) <= 3): cmd_sess()
else: cmd_sess()
