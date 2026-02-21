"""Shared utilities for aio commands - like git's libgit"""
import sys, os, subprocess as sp, sqlite3, json, shutil, time, socket
from datetime import datetime
from pathlib import Path

# Constants
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ADATA_ROOT = next((p for p in [Path(SCRIPT_DIR) / 'adata', Path.home() / 'projects' / 'a' / 'adata', Path.home() / 'adata'] if (p / 'git').exists()), Path(SCRIPT_DIR) / 'adata')
PROMPTS_DIR = ADATA_ROOT / 'git' / 'common' / 'prompts'
DATA_DIR = str(ADATA_ROOT / 'local')
DB_PATH = os.path.join(DATA_DIR, "aio.db")
SYNC_ROOT = ADATA_ROOT / 'git'
def _get_dev():
    f = os.path.join(DATA_DIR, '.device')
    if os.path.exists(f): return open(f).read().strip()
    d = (sp.run(['getprop','ro.product.model'],capture_output=True,text=True).stdout.strip().replace(' ','-') or socket.gethostname()) if os.path.exists('/data/data/com.termux') else socket.gethostname()
    os.makedirs(os.path.dirname(f), exist_ok=True); open(f,'w').write(d)
    return d
DEVICE_ID = _get_dev()
LOG_DIR = str(ADATA_ROOT / 'backup' / DEVICE_ID)
_GP, _GT = '_aio_ghost_', 300
_GM = {'c': 'l', 'l': 'l', 'g': 'g', 'o': 'l', 'co': 'c', 'cp': 'c', 'lp': 'l', 'gp': 'g'}
_AIO_DIR = os.path.expanduser('~/.a')
_AIO_CONF = os.path.join(_AIO_DIR, 'tmux.conf')
_USER_CONF = os.path.expanduser('~/.tmux.conf')
_SRC_LINE = 'source-file ~/.a/tmux.conf  # a'
RCLONE_REMOTE_PREFIX, RCLONE_BACKUP_PATH = 'a-gdrive', 'adata'
ACTIVITY_DIR = ADATA_ROOT / 'git' / 'activity'

def alog(msg):
    """Append activity log entry (individual file, append-only)"""
    ACTIVITY_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    ms = int(now.timestamp() * 1000) % 1000
    fn = now.strftime(f'%Y%m%dT%H%M%S.{ms:03d}_{DEVICE_ID}.txt')
    cwd = os.getcwd()
    repo = ''
    if os.path.isdir(os.path.join(cwd, '.git')):
        r = sp.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True, cwd=cwd)
        if r.returncode == 0 and r.stdout.strip(): repo = f' git:{r.stdout.strip()}'
    (ACTIVITY_DIR / fn).write_text(f'{now:%m/%d %H:%M} {DEVICE_ID} {msg} {cwd}{repo}\n')

# Basic helpers
def _git(path, *a, **k): return sp.run(['git', '-C', path] + list(a), capture_output=True, text=True, **k)
def _tmux(*a): return sp.run(['tmux'] + list(a), capture_output=True, text=True)
def _ok(m): print(f"✓ {m}")
def _err(m): print(f"x {m}")
def _die(m, c=1): _err(m); sys.exit(c)
def _confirm(m): return input(f"{m} (y/n): ").strip().lower() in ['y', 'yes']
def _up(h):
    try: s=socket.socket(); s.settimeout(0.5); hp=h.rsplit(':',1); return not s.connect_ex((hp[0].split('@')[-1], int(hp[1]) if len(hp)>1 else 22))
    except: return False
def _in_repo(p):
    while p != '/' and not os.path.exists(p+'/.git'): p = os.path.dirname(p)
    return p != '/'

# Tmux wrapper
class TM:
    def __init__(self): self._v = None
    def new(self, n, d, c, e=None): return sp.run(['tmux', 'new-session', '-d', '-s', n, '-c', d] + ([c] if c else []), capture_output=True, env=e)
    def send(self, n, t): return sp.run(['tmux', 'send-keys', '-l', '-t', n, t])
    def attach(self, n): return ['tmux', 'attach', '-t', n]
    def go(self, n): os.execvp('tmux', ['tmux', 'switch-client' if 'TMUX' in os.environ else 'attach', '-t', n])
    def has(self, n):
        try: return sp.run(['tmux', 'has-session', '-t', n], capture_output=True, timeout=2).returncode == 0
        except sp.TimeoutExpired: print("! tmux hung, killing..."); sp.run(['pkill', '-9', 'tmux']); return False
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
# Database
def db(): c = sqlite3.connect(DB_PATH); c.execute("PRAGMA journal_mode=WAL;"); return c

def get_prompt(name, show=False):
    pf = PROMPTS_DIR / f'{name}.txt'
    if pf.exists():
        show and print(f"Prompt: {pf}")
        return pf.read_text(errors='replace').strip()
    return None

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, display_order INTEGER NOT NULL, device TEXT DEFAULT '*')")
        c.execute("CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, command TEXT NOT NULL, display_order INTEGER NOT NULL, device TEXT DEFAULT '*')")
        for t in ['projects', 'apps']:
            if 'device' not in [r[1] for r in c.execute(f"PRAGMA table_info({t})")]: c.execute(f"ALTER TABLE {t} ADD COLUMN device TEXT DEFAULT '*'")
        c.execute("CREATE TABLE IF NOT EXISTS sessions(key TEXT PRIMARY KEY,name TEXT NOT NULL,command_template TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS multi_runs (id TEXT PRIMARY KEY, repo TEXT NOT NULL, prompt TEXT NOT NULL, agents TEXT NOT NULL, status TEXT DEFAULT 'running', created_at TEXT DEFAULT CURRENT_TIMESTAMP, review_rank TEXT)")
        (t:=c.execute("PRAGMA table_info(notes)").fetchall())and(t[0][2]=='INTEGER'and c.execute("DROP TABLE notes")or'dev'not in[r[1]for r in t]and c.execute("ALTER TABLE notes ADD dev"))
        c.execute("CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,t,s DEFAULT 0,d,c DEFAULT CURRENT_TIMESTAMP,proj,dev)")
        c.execute("CREATE TABLE IF NOT EXISTS note_projects(id INTEGER PRIMARY KEY,name TEXT UNIQUE,c TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, real_deadline INTEGER NOT NULL, virtual_deadline INTEGER, created_at INTEGER NOT NULL, completed_at INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS jobs(name TEXT PRIMARY KEY,step TEXT NOT NULL,status TEXT NOT NULL,path TEXT,session TEXT,updated_at INTEGER NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS hub_jobs (id INTEGER PRIMARY KEY, name TEXT, schedule TEXT, prompt TEXT, agent TEXT DEFAULT 'l', project TEXT, device TEXT, enabled INTEGER DEFAULT 1, last_run TEXT, parallel INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS agent_logs(session TEXT PRIMARY KEY,parent TEXT,started REAL,device TEXT)")
        if 'device' not in [r[1] for r in c.execute("PRAGMA table_info(agent_logs)")]: c.execute("ALTER TABLE agent_logs ADD COLUMN device TEXT")
        if c.execute("SELECT COUNT(*) FROM config").fetchone()[0] == 0:
            dp = get_prompt('default') or ''
            for k, v in [('claude_prompt', dp), ('codex_prompt', dp), ('gemini_prompt', dp), ('worktrees_dir', os.path.expanduser("~/projects/a/adata/worktrees")), ('multi_default', 'l:3')]: c.execute("INSERT INTO config VALUES (?, ?)", (k, v))
        c.execute("INSERT OR IGNORE INTO config VALUES ('multi_default', 'l:3')")
        c.execute("INSERT OR IGNORE INTO config VALUES ('claude_prefix', 'Ultrathink. ')")
        np = not c.execute("SELECT 1 FROM projects").fetchone()
        if np:
            for p in [SCRIPT_DIR, os.path.expanduser("~/aio"), os.path.expanduser("~/projects/aio")]:
                if os.path.isdir(p) and os.path.isdir(os.path.join(p, ".git")): c.execute("INSERT INTO projects(path,display_order,device)VALUES(?,0,'*')",(p,)); break
        if np or not c.execute("SELECT 1 FROM apps").fetchone():
            ui = next((p for p in [os.path.join(SCRIPT_DIR, "aioUI.py"), os.path.expanduser("~/aio/aioUI.py"), os.path.expanduser("~/.local/bin/aioUI.py")] if os.path.exists(p)), None)
            if ui: c.execute("INSERT INTO apps(name,command,display_order,device)VALUES(?,?,0,'*')",("aioUI",f"python3 {ui}"))
        if c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0:
            cdx, cld = 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox', 'claude --dangerously-skip-permissions'
            for k, n, t in [('h','htop','htop'),('t','top','top'),('g','gemini','gemini --yolo'),('gemini','gemini','gemini --yolo'),('gp','gemini-p','gemini --yolo "{GEMINI_PROMPT}"'),('c','claude',cld),('claude','claude',cld),('cp','claude-p',f'{cld} "{{CLAUDE_PROMPT}}"'),('l','claude',cld),('lp','claude-p',f'{cld} "{{CLAUDE_PROMPT}}"'),('o','claude',cld),('co','codex',cdx),('codex','codex',cdx),('cop','codex-p',f'{cdx} "{{CODEX_PROMPT}}"'),('a','aider','OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral')]:
                c.execute("INSERT INTO sessions VALUES (?, ?, ?)", (k, n, t))
        c.execute("INSERT OR IGNORE INTO sessions VALUES ('o', 'claude', 'claude --dangerously-skip-permissions')")
        c.execute("INSERT OR IGNORE INTO sessions VALUES ('a', 'aider', 'OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral')")
        c.commit()

def load_cfg():
    p = os.path.join(DATA_DIR, "config.txt")
    if os.path.exists(p):
        return {k.strip(): v.strip().replace('\\n', '\n') for line in open(p).read().splitlines() if ':' in line for k, v in [line.split(':', 1)]}
    with db() as c: return dict(c.execute("SELECT key, value FROM config").fetchall())

def load_proj():
    proj_dir = SYNC_ROOT / 'workspace' / 'projects'; proj_dir.mkdir(parents=True, exist_ok=True); projs = []
    for f in proj_dir.glob('*.txt'):
        d = {k.strip(): v.strip() for line in f.read_text().splitlines() if ':' in line for k, v in [line.split(':', 1)]}
        if 'Name' in d: projs.append((d.get('Path', f'~/projects/{d["Name"]}'), d.get('Repo', ''), d['Name']))
    return [(os.path.expanduser(p), r) for p, r, n in sorted(projs, key=lambda x: x[2])]

def load_apps():
    cmds_dir = SYNC_ROOT / 'workspace' / 'cmds'; cmds_dir.mkdir(parents=True, exist_ok=True); cmds = []
    for f in cmds_dir.glob('*.txt'):
        d = {k.strip(): v.strip() for line in f.read_text().splitlines() if ':' in line for k, v in [line.split(':', 1)]}
        if 'Name' in d and 'Command' in d: cmds.append((d['Name'], d['Command']))
    return sorted(cmds, key=lambda x: x[0])

def resolve_cmd(cmd):
    import re
    projs = {os.path.basename(p): p for p, _ in load_proj()}
    return re.sub(r'\{(\w+)\}', lambda m: projs.get(m.group(1), m.group(0)), cmd)

def load_sess(cfg):
    p = os.path.join(DATA_DIR, "sessions.txt")
    if os.path.exists(p):
        data = [line.split('|', 2) for line in open(p).read().splitlines() if '|' in line]
        data = [(r[0], r[1], r[2]) for r in data if len(r) == 3]
    else:
        with db() as c: data = c.execute("SELECT key, name, command_template FROM sessions").fetchall()
    dp, s = get_prompt('default'), {}
    esc = lambda p: cfg.get(p, dp or '').replace('\n', '\\n').replace('"', '\\"')
    for k, n, t in data:
        s[k] = (n, t.replace(' "{CLAUDE_PROMPT}"', '').replace(' "{CODEX_PROMPT}"', '').replace(' "{GEMINI_PROMPT}"', '') if k in ['cp','lp','gp'] else t.format(CLAUDE_PROMPT=esc('claude_prompt'), CODEX_PROMPT=esc('codex_prompt'), GEMINI_PROMPT=esc('gemini_prompt')))
    return s

def _pmark(p,r): return '+' if os.path.exists(p) else ('~' if r else 'x')
def _refresh_cache():
    from .update import refresh_caches; refresh_caches()

def add_proj(p):
    from .sync import sync
    p = os.path.abspath(os.path.expanduser(p))
    if not os.path.isdir(p): return False, f"Not a directory: {p}"
    name = os.path.basename(p)
    d = SYNC_ROOT / 'workspace' / 'projects'; d.mkdir(parents=True, exist_ok=True)
    if (d/f'{name}.txt').exists(): return False, f"Exists: {name}"
    repo = sp.run(['git','-C',p,'remote','get-url','origin'],capture_output=True,text=True).stdout.strip()
    (d/f'{name}.txt').write_text(f"Name: {name}\n" + (f"Repo: {repo}\n" if repo else "")); sync('workspace')
    _refresh_cache(); return True, f"Added: {name}"

def rm_proj(i):
    from .sync import sync
    projs = load_proj()
    if i < 0 or i >= len(projs): return False, f"Invalid index: {i}"
    name = os.path.basename(projs[i][0])
    (SYNC_ROOT/'workspace'/'projects'/f'{name}.txt').unlink(missing_ok=True); sync('workspace')
    _refresh_cache(); return True, f"Removed: {name}"

def add_app(n, cmd):
    if not n or not cmd: return False, "Name and command required"
    from .sync import sync, SYNC_ROOT
    d = SYNC_ROOT / 'workspace' / 'cmds'; d.mkdir(parents=True, exist_ok=True)
    if (d/f'{n}.txt').exists(): return False, f"Exists: {n}"
    (d/f'{n}.txt').write_text(f"Name: {n}\nCommand: {cmd}\n"); sync('workspace')
    _refresh_cache(); return True, f"Added: {n}"

def rm_app(i):
    from .sync import sync, SYNC_ROOT
    a = load_apps()
    if i < 0 or i >= len(a): return False, f"Invalid index: {i}"
    n = a[i][0]; (SYNC_ROOT/'workspace'/'cmds'/f'{n}.txt').unlink(missing_ok=True); sync('workspace')
    _refresh_cache(); return True, f"Removed: {n}"

def fmt_cmd(c, mx=60):
    d = c.replace(os.path.expanduser('~'), '~')
    return d[:mx-3] + "..." if len(d) > mx else d

# Cloud sync
def get_rclone(): return shutil.which('rclone') or next((p for p in ['/usr/bin/rclone', os.path.expanduser('~/.local/bin/rclone')] if os.path.isfile(p)), None)
def _configured_remotes():
    if not (rc := get_rclone()): return []
    r = sp.run([rc, 'listremotes'], capture_output=True, text=True)
    if r.returncode != 0: return []
    return [l.rstrip(':') for l in r.stdout.splitlines() if l.rstrip(':').startswith(RCLONE_REMOTE_PREFIX)]
def cloud_account(remote=None):
    if not (rc := get_rclone()): return "(no rclone)"
    try:
        rem = remote or _configured_remotes()[0]
        if sp.run([rc, 'about', f'{rem}:'], capture_output=True, timeout=10).returncode != 0: return "(token expired)"
        token = json.loads(json.loads(sp.run([rc, 'config', 'dump'], capture_output=True, text=True).stdout).get(rem, {}).get('token', '{}')).get('access_token')
        u = json.loads(__import__('urllib.request').request.urlopen(__import__('urllib.request').request.Request('https://www.googleapis.com/drive/v3/about?fields=user', headers={'Authorization': f'Bearer {token}'}), timeout=5).read()).get('user', {})
        return f"{u.get('displayName', '')} <{u.get('emailAddress', 'unknown')}>"
    except sp.TimeoutExpired: return "(offline)"
    except: return "(error)"
def cloud_sync(wait=False):
    rc, remotes = get_rclone(), _configured_remotes()
    if not rc or not remotes: return False, None
    def _sync():
        ok = True
        for rem in remotes:
            r = sp.run([rc, 'copy', DATA_DIR, f'{rem}:{RCLONE_BACKUP_PATH}/backup/data', '-q', '--exclude', '*.db*', '--exclude', '*cache*', '--exclude', 'timing.jsonl', '--exclude', '.device', '--exclude', '.git/**', '--exclude', 'logs/**'], capture_output=True, text=True)
            for f in ['~/.config/gh/hosts.yml', '~/.config/rclone/rclone.conf']:
                p = os.path.expanduser(f); os.path.exists(p) and sp.run([rc, 'copy', p, f'{rem}:{RCLONE_BACKUP_PATH}/backup/auth/', '-q'], capture_output=True)
            ok = ok and r.returncode == 0
        Path(DATA_DIR, '.gdrive_sync').touch() if ok else None; return ok
    return (True, _sync()) if wait else (__import__('threading').Thread(target=_sync, daemon=True).start(), (True, None))[1]
def cloud_install():
    u=os.uname();s,bd,arch='osx'if u.sysname=='Darwin'else'linux',os.path.expanduser('~/.local/bin'),'amd64'if u.machine in('x86_64','AMD64')else'arm64'
    print(f"Installing rclone..."); os.makedirs(bd, exist_ok=True)
    if sp.run(f'curl -sL https://downloads.rclone.org/rclone-current-{s}-{arch}.zip -o /tmp/rclone.zip && unzip -qjo /tmp/rclone.zip "*/rclone" -d {bd} && chmod +x {bd}/rclone', shell=True).returncode == 0:
        print(f"✓ Installed"); return f'{bd}/rclone'
    return None
def _next_remote_name():
    existing = _configured_remotes()
    if RCLONE_REMOTE_PREFIX not in existing: return RCLONE_REMOTE_PREFIX
    i = 2
    while f'{RCLONE_REMOTE_PREFIX}{i}' in existing: i += 1
    return f'{RCLONE_REMOTE_PREFIX}{i}'
def cloud_login(remote=None, custom=False):
    rc = get_rclone() or cloud_install()
    if not rc: print("✗ rclone install failed"); return False
    rem = remote or _next_remote_name()
    cmd = [rc, 'config', 'create', rem, 'drive']
    if custom:
        print("""Setup your own Google OAuth key (faster, dedicated quota):

  1. Go to https://console.cloud.google.com/
  2. Create a project (or pick one)
  3. APIs & Services → Enable "Google Drive API"
  4. APIs & Services → OAuth consent screen → Get Started
     - App name: anything, your email for support/contact
     - Audience: External → add your email as test user (lowercase)
  5. APIs & Services → Credentials → Create Credentials → OAuth client ID
     - Type: Desktop app
     - Name: anything (e.g. "rclone")
  6. Copy the client_id and client_secret below
""")
        cid = input("client_id: ").strip(); csec = input("client_secret: ").strip()
        if not cid or not csec: print("✗ Both client_id and client_secret required"); return False
        cmd += ['client_id', cid, 'client_secret', csec]
    sp.run(cmd)
    if rem not in _configured_remotes(): print("✗ Login failed - try again"); return False
    print(f"✓ Logged in {rem} as {cloud_account(rem) or 'unknown'}"); cloud_sync(wait=True); open(f"{DATA_DIR}/.auth_local", "w").close(); Path(f"{DATA_DIR}/.auth_shared").unlink(missing_ok=True)
    aio = os.path.join(SCRIPT_DIR, 'aio.py')
    if not db().execute("SELECT 1 FROM hub_jobs WHERE name='gdrive-sync'").fetchone():
        sp.run([sys.executable, aio, 'hub', 'add', 'gdrive-sync', '*:0/30', 'aio', 'gdrive', 'sync'])
    return True
def cloud_logout(remote=None):
    remotes = _configured_remotes()
    if not remotes: print("Not logged in"); return False
    rem = remote or remotes[-1]
    sp.run([get_rclone(), 'config', 'delete', rem]); print(f"✓ Logged out {rem}"); return True
def _cloud_storage(remote):
    rc = get_rclone()
    if not rc: return ""
    try:
        r = sp.run([rc, 'about', f'{remote}:', '--json'], capture_output=True, text=True, timeout=10)
        if r.returncode != 0: return ""
        d = json.loads(r.stdout); used, total = d.get('used', 0), d.get('total', 0)
        def _h(b):
            for u in ('B','KiB','MiB','GiB','TiB'):
                if b < 1024: return f"{b:.1f} {u}"
                b /= 1024
            return f"{b:.1f} PiB"
        return f" ({_h(used)} / {_h(total)})"
    except: return ""
def _all_drive_remotes():
    rc = get_rclone()
    if not rc: return {}
    try:
        d = json.loads(sp.run([rc, 'config', 'dump'], capture_output=True, text=True).stdout)
        return {k: v for k, v in d.items() if v.get('type') == 'drive'}
    except: return {}
def cloud_status():
    remotes = _configured_remotes()
    all_rem = _all_drive_remotes()
    if all_rem:
        for rem, cfg in all_rem.items():
            tag = "✓" if rem in remotes else "·"
            key = "custom" if cfg.get('client_id') else "shared"
            print(f"{tag} {rem}: {cloud_account(rem)}{_cloud_storage(rem)} [{key} key]")
        print(f"\n{len(remotes)} synced. Add more: a gdrive login")
        return True
    print("✗ Not logged in\n\nSetup: a gdrive login"); return False

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
    sf = '#[range=user|agent]Ctrl+A:Agent#[norange] #[range=user|win]Ctrl+N:Win#[norange] #[range=user|new]Ctrl+T:Pane#[norange] #[range=user|side]Ctrl+Y:Side#[norange] #[range=user|close]Ctrl+W:Close#[norange] #[range=user|edit]Ctrl+E:Edit#[norange] #[range=user|detach]Ctrl+Q:Quit#[norange]'
    sm = '#[range=user|agent]Agent#[norange] #[range=user|win]Win#[norange] #[range=user|new]Pane#[norange] #[range=user|side]Side#[norange] #[range=user|close]Close#[norange] #[range=user|edit]Edit#[norange] #[range=user|detach]Quit#[norange]'
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
bind-key -n C-y split-window -fh
bind-key -n C-a split-window -h 'claude --dangerously-skip-permissions'
bind-key -n C-w kill-pane
bind-key -n C-q detach
bind-key -n C-x confirm-before -p "Kill session? (y/n)" kill-session
bind-key -n C-e split-window -fh -c '#{{pane_current_path}}' ~/.local/bin/e
bind-key -T root MouseDown1Status if -F '#{{==:#{{mouse_status_range}},window}}' {{ select-window }} {{ run-shell 'r="#{{mouse_status_range}}"; case "$r" in agent) tmux split-window -h "claude --dangerously-skip-permissions";; win) tmux new-window;; new) tmux split-window;; side) tmux split-window -fh;; close) tmux kill-pane;; edit) tmux split-window -fh -c "#{{pane_current_path}}" ~/.local/bin/e;; detach) tmux detach;; esc) tmux send-keys Escape;; kbd) tmux set -g mouse off; tmux display-message "Mouse off 3s"; (sleep 3; tmux set -g mouse on) &;; esac' }}
'''
    conf += f'set -s copy-command "{cc}"\n' if cc else ''; cq=f' "{cc}"'if cc else''
    conf += f'bind -T copy-mode MouseDragEnd1Pane send -X copy-pipe-and-cancel{cq}\nbind -T copy-mode-vi MouseDragEnd1Pane send -X copy-pipe-and-cancel{cq}\n'
    if tm.ver >= '3.6': conf += 'set -g pane-scrollbars on\nset -g pane-scrollbars-position right\n'
    os.makedirs(_AIO_DIR, exist_ok=True)
    with open(_AIO_CONF, 'w') as f: f.write(conf)
    uc = Path(_USER_CONF).read_text() if os.path.exists(_USER_CONF) else ''
    if _SRC_LINE not in uc and '~/.a/tmux.conf' not in uc:
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

def create_sess(sn, wd, cmd, cfg, env=None, skip_prefix=False):
    ai = cmd and any(a in cmd for a in ['codex', 'claude', 'gemini', 'aider'])
    if ai: cmd = f'while :; do {cmd}; e=$?; [ $e -eq 0 ] && break; echo -e "\\n! Crashed (exit $e). [R]estart / [Q]uit: "; read -n1 k; [[ $k =~ [Rr] ]] || break; done'
    r = tm.new(sn, wd, cmd or '', env); ensure_tmux(cfg)
    if ai: sp.run(['tmux', 'split-window', '-v'] + (['-p', '40'] if os.environ.get('TERMUX_VERSION') else []) + ['-t', sn, '-c', wd, 'sh -c "ls;exec $SHELL"'], capture_output=True); sp.run(['tmux', 'select-pane', '-t', sn, '-U'], capture_output=True)
    _start_log(sn)
    return r

def is_active(sn, thr=10):
    r = sp.run(['tmux', 'display-message', '-p', '-t', sn, '#{window_activity}'], capture_output=True, text=True)
    if r.returncode != 0: return False
    try: return int(time.time()) - int(r.stdout.strip()) < thr
    except: return False

def get_prefix(agent, cfg, wd=None):
    dp = get_prompt('default') or ''
    pre = cfg.get('claude_prefix', 'Ultrathink. ') if 'claude' in agent else ''
    af = Path(wd or os.getcwd()) / 'AGENTS.md'
    return (dp + ' ' if dp else '') + pre + (af.read_text().strip() + ' ' if af.exists() else '')

def send_prefix(sn, agent, wd, cfg, prompt=None):
    if prompt:
        # prompt mode: accept bypass confirmation, wait for ❯ prompt, send prompt + Enter
        script = f'import time,subprocess as s\nfor _ in range(600):\n time.sleep(0.1);r=s.run(["tmux","capture-pane","-t","{sn}","-p"],capture_output=True,text=True)\n if "bypass" in r.stdout.lower():s.run(["tmux","send-keys","-t","{sn}","Enter"]);time.sleep(5);break\n if "\\u276f" in r.stdout:break\ns.run(["tmux","send-keys","-l","-t","{sn}",{repr(prompt)}])\ntime.sleep(0.1);s.run(["tmux","send-keys","-t","{sn}","Enter"])'
    else:
        pre = get_prefix(agent, cfg, wd)
        if not pre: return
        script = f'import time,subprocess as s\nfor _ in range(300):\n time.sleep(0.05);r=s.run(["tmux","capture-pane","-t","{sn}","-p","-S","-50"],capture_output=True,text=True);o=r.stdout.lower()\n if r.returncode!=0 or any(x in o for x in["context","claude","opus","gemini","codex"]):break\ns.run(["tmux","send-keys","-l","-t","{sn}",{repr(pre)}])'
    sp.Popen([sys.executable, '-c', script], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

def send_to_sess(sn, prompt, wait=False, timeout=None, enter=True):
    if not tm.has(sn): print(f"x Session {sn} not found"); return False
    tm.send(sn, prompt)
    if enter: time.sleep(0.1); sp.run(['tmux', 'send-keys', '-t', sn, 'Enter']); print(f"✓ Sent to '{sn}'")
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

# Help text
HELP_SHORT = """a c|co|g|ai     Start claude/codex/gemini/aider
a <#>           Open project by number
a prompt        Manage default prompt
a help          All commands"""

HELP_FULL = """a - AI agent session manager

AGENTS          c=claude  co=codex  g=gemini  ai=aider
  a <key>             Start agent in current dir
  a <key> <#>         Start agent in project #
  a <key>++           Start agent in new worktree

PROJECTS
  a <#>               cd to project #
  a add               Add current dir as project
  a remove <#>        Remove project
  a move <#> <#>      Reorder project
  a scan              Add your repos fast

GIT
  a push [msg]        Commit and push
  a pull              Sync with remote
  a diff              Show changes
  a revert            Select commit to revert to

REMOTE
  a ssh               List hosts
  a ssh <#>           Connect to host
  a run <#> "task"    Run task on remote

OTHER
  a jobs              Active sessions
  a ls                List tmux sessions
  a attach            Reconnect to session
  a kill              Kill all sessions
  a task              Tasks (priority, review, subfolders)
  a n "text"          Quick note
  a log               View agent logs
  a config            View/set settings
  a update [shell|cache]  Update a (or just shell/cache)
  a mono              Generate monolith for reading

EXPERIMENTAL
  a agent "task"      Spawn autonomous subagent
  a hub               Scheduled jobs (systemd)
  a all               Multi-agent parallel runs
  a tree              Create git worktree
  a gdrive            Cloud sync (Google Drive)"""

def list_all(cache=True, quiet=False):
    import subprocess as sp
    ws = SYNC_ROOT / 'workspace'; url = sp.run(['git','-C',str(ws),'remote','get-url','origin'], capture_output=True, text=True).stdout.strip()
    p, a = load_proj(), load_apps(); Path(os.path.join(DATA_DIR, 'projects.txt')).write_text('\n'.join(x for x,_ in p) + '\n')
    out = [f"Workspace: {ws}", f"  {url}", ""] if url else []
    out += ([f"PROJECTS:"] + [f"  {i}. {_pmark(x,r)} {x}" for i,(x,r) in enumerate(p)] if p else [])
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
