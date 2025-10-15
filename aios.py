#!/usr/bin/env python3
"""AIOS Task Manager - git-inspired design

Usage: aios [--profile] [--simple|-s] [--test] [--update] [--auto-update-on|--auto-update-off] [task.json|prompt ...]

Modes:
    Default: Interactive TUI (running tasks view)
    Immediate Prompt: Start typing your prompt directly (workflow selection with codex default)
    --profile: Profile functions and save baseline timings
    --simple: Batch execution with simple monitoring
    --test: Run built-in tests
    --update: Update AIOS to latest version
    --auto-update-on: Enable automatic background updates (checks once per day)
    --auto-update-off: Disable automatic background updates

Examples:
    aios                              # TUI mode (running tasks default)
    aios create a fibonacci function  # Immediate prompt mode (select workflow, auto-fill vars)
    aios task.json                    # Load task, run in TUI
    aios --simple task.json           # Batch mode
    echo "fix bug X" | aios           # Paste/pipe prompt
    aios --test                       # Run tests
    aios --update                     # Self-update
    aios --auto-update-on             # Enable auto-updates

Commands in TUI:
    #                       - Watch job live in terminal (e.g., "1" to watch job 1)
    m                       - Show workflow menu
    a <#|name>              - Attach to job in browser terminal
    o <#|name>              - Open job in editor (VS Code by default)
    r <job>                 - Run job from builder
    c <job>                 - Clear job from builder
    t +<title> <dl> [vd]    - Add todo
    t ✓<id>                 - Complete todo
    t ✗<id>                 - Delete todo
    q                       - Quit
"""

import libtmux, json, sys, re, shutil, asyncio, websockets, webbrowser, subprocess, pty, fcntl, termios, struct, os, signal, sqlite3, urllib.request
from datetime import datetime
from time import sleep, time
from threading import Thread, Lock
from queue import Queue, Empty
from pathlib import Path
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from http.server import HTTPServer, BaseHTTPRequestHandler
from functools import wraps
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Global state
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
server, jobs, jobs_lock = libtmux.Server(), {}, Lock()
task_queue, task_builder, builder_lock = Queue(), {}, Lock()
running, processed_files, processed_files_lock = True, set(), Lock()
ws_port, ws_server_running = 7681, False
JOBS_DIR, MAX_JOB_DIRS = Path("jobs"), 20
_terminal_sessions = {}
TIMINGS_FILE, profile_mode = DATA_DIR / "timings.json", "--profile" in sys.argv
DB_FILE, todos, todos_lock, notification_queue = DATA_DIR / "aios.db", {}, Lock(), Queue()
CONFIG_FILE = DATA_DIR / "config.json"

# Config management (auto-update settings)
def load_config():
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            cfg.setdefault("editor_command", "code .")
            return cfg
        except: pass
    return {"auto_update": False, "last_update_check": 0, "check_interval": 86400, "editor_command": "code ."}

def save_config(config):
    try: CONFIG_FILE.write_text(json.dumps(config, indent=2))
    except: pass

config = load_config()

# Coding standards template
CODING_STANDARDS = """Write the following as short as possible while following the below.

Make line count minimal as possible while doing exactly the same things, use direct library calls as often as possible, keep it readable and follow all program readability conventions, for technical issues think about what exactly does the most popular app or program of all in the world that is similar to this does, and manually run debug and inspect output and fix issues for each function or changed section one by one then together before finishing.
The specific inspiration for any technical decision that is complex and interface is what git, claudecode, codex, top, does.
If rewriting existing sections of code with no features added, each change must be readable and follow all program readability conventions, run as fast or faster than previous code, lower in line count or equal to original, use the same or greater number of direct library calls, reduce the number of states the program could be in or keep it equal, make it simpler or the same complexity than before.
Specific practices:
No polling whatsoever, only event based."""

# Performance enforcement
load_timings = lambda: json.loads(TIMINGS_FILE.read_text()) if TIMINGS_FILE.exists() else {}
save_timings = lambda t: TIMINGS_FILE.write_text(json.dumps(t, indent=2))
timings_baseline = {} if profile_mode else load_timings()
timings_current = {}

def timed(func):
    """Decorator: Time AIOS overhead. SIGKILL if > baseline + 0.5ms"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time()
        result = func(*args, **kwargs)
        elapsed, fname = time() - start, func.__name__
        if profile_mode:
            timings_current[fname] = elapsed
        elif fname in timings_baseline and elapsed > timings_baseline[fname] + 0.0005:
            print(f"\n✗ PERF REGRESSION: {fname} {elapsed*1000:.2f}ms (baseline {timings_baseline[fname]*1000:.2f}ms, +{(elapsed-timings_baseline[fname])*1000:.2f}ms over)")
            os.kill(os.getpid(), signal.SIGKILL)
        return result
    return wrapper

# Todo DB
def init_db():
    with sqlite3.connect(DB_FILE) as db:
        db.execute('CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, real_deadline INTEGER NOT NULL, virtual_deadline INTEGER, created_at INTEGER NOT NULL, completed_at INTEGER)')

@timed
def get_todos():
    with sqlite3.connect(DB_FILE) as db:
        return db.execute('SELECT id,title,real_deadline,virtual_deadline,created_at FROM todos WHERE completed_at IS NULL ORDER BY real_deadline').fetchall()

def add_todo(title, real_deadline, virtual_deadline=None):
    now = int(time())
    with sqlite3.connect(DB_FILE) as db:
        todo_id = db.execute('INSERT INTO todos (title,real_deadline,virtual_deadline,created_at) VALUES (?,?,?,?)', (title, real_deadline, virtual_deadline, now)).lastrowid
    if virtual_deadline: notification_queue.put(('virtual', todo_id, virtual_deadline))
    notification_queue.put(('real', todo_id, real_deadline))
    load_todos()
    return todo_id

def complete_todo(todo_id):
    with sqlite3.connect(DB_FILE) as db: db.execute('UPDATE todos SET completed_at=? WHERE id=?', (int(time()), todo_id))
    load_todos()

def delete_todo(todo_id):
    with sqlite3.connect(DB_FILE) as db: db.execute('DELETE FROM todos WHERE id=?', (todo_id,))
    load_todos()

@timed
def load_todos():
    with todos_lock:
        todos.clear()
        for id, title, rd, vd, ca in get_todos():
            todos[id] = {'title': title, 'real_deadline': rd, 'virtual_deadline': vd, 'created_at': ca}

@timed
def get_urgency_style(deadline):
    delta = deadline - time()
    if delta < 0: return 'class:error', '⚠ OVERDUE'
    if delta < 3600: return 'class:error', f'⏰ {int(delta/60)}m'
    if delta < 86400: return 'class:running', f'⏰ {int(delta/3600)}h'
    return 'class:dim', f'⏰ {int(delta/86400)}d'

backup_db = lambda: shutil.copy2(DB_FILE, DB_FILE.with_suffix(f'.{datetime.now().strftime("%Y%m%d_%H%M%S")}.bak')) if DB_FILE.exists() else None
parse_deadline = lambda s: int(time()) + int(s[:-1]) * {'m': 60, 'h': 3600, 'd': 86400}[s[-1]] if s[-1] in 'mhd' and s[:-1].isdigit() else int(datetime.fromisoformat(s).timestamp()) if '-' in s else int(s)
is_deadline = lambda s: (s[-1] in 'mhd' and s[:-1].isdigit()) or '-' in s or s.isdigit()

def notification_worker():
    """Event-driven notification system"""
    scheduled = {}
    while running:
        try:
            try:
                while True:
                    typ, todo_id, timestamp = notification_queue.get_nowait()
                    scheduled[(typ, todo_id)] = timestamp
            except Empty: pass
            now, due = time(), [(k, v) for k, v in scheduled.items() if v <= now]
            for (typ, todo_id), ts in due:
                with todos_lock:
                    if todo_id in todos:
                        title = todos[todo_id]['title']
                        print(f"\n{'🔔 TODO ALERT' if typ == 'virtual' else '🚨 TODO URGENT'}: {title}")
                del scheduled[(typ, todo_id)]
            sleep(max(0.1, min(60, min(scheduled.values()) - time())) if scheduled else 60)
        except: continue

# Core functions
@timed
def extract_variables(obj):
    if isinstance(obj, str): return set(re.findall(r'\{\{(\w+)\}\}', obj))
    if isinstance(obj, dict): return set().union(*(extract_variables(v) for v in obj.values()))
    if isinstance(obj, list): return set().union(*(extract_variables(i) for i in obj))
    return set()

@timed
def substitute_variables(obj, values):
    if isinstance(obj, str): return re.sub(r'\{\{(\w+)\}\}', lambda m: str(values.get(m.group(1), m.group(0))), obj)
    if isinstance(obj, dict): return {k: substitute_variables(v, values) for k, v in obj.items()}
    if isinstance(obj, list): return [substitute_variables(i, values) for i in obj]
    return obj

def prompt_for_variables(task):
    if not (variables := extract_variables(task)): return task
    defaults, sep = task.get('variables', {}), "="*80
    print(f"\n{sep}\nTEMPLATE PREVIEW\n{sep}\n{json.dumps(task, indent=2)}\n{sep}\n{sep}\nDEFAULTS\n{sep}")
    for var in sorted(variables):
        d = defaults.get(var, '(no default)')
        print(f"  {var}: {str(d)[:60]+'...' if len(str(d))>60 else d}")
    print(f"{sep}\n{sep}\nVARIABLES\n{sep}")
    values = {}
    for var in sorted(variables):
        default, prompt_text = defaults.get(var, ''), f"{var} [{str(default)[:30]+'...' if len(str(default))>30 else str(default)}]: " if default else f"{var}: "
        values[var] = (user_input := input(prompt_text).strip()) if user_input else default
    sub = substitute_variables(task, values)
    print(f"{sep}\n{sep}\nFINAL\n{sep}\n{json.dumps(sub, indent=2)}\n{sep}")
    return None if (c := input("Launch? [Y/n]: ").strip().lower()) and c not in ['y', 'yes'] else sub

cleanup_old_jobs = lambda: [shutil.rmtree(d) for d in sorted(JOBS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[MAX_JOB_DIRS:]] if JOBS_DIR.exists() else None
get_session = lambda name: next((s for s in server.sessions if s.name == name), None)
kill_session = lambda name: get_session(name).kill() if get_session(name) else None

def execute_task(task):
    """Event-driven execution in real tmux session"""
    name, steps, repo, branch = task["name"], task["steps"], task.get("repo"), task.get("branch", "main")
    ts, session_name = datetime.now().strftime("%Y%m%d_%H%M%S"), f"aios-{name}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    JOBS_DIR.mkdir(exist_ok=True)
    job_dir, worktree_dir = JOBS_DIR / f"{name}-{ts}", (JOBS_DIR / f"{name}-{ts}" / "worktree") if repo else None
    work_path = str(worktree_dir.absolute()) if repo else str(job_dir.absolute())
    try:
        with jobs_lock: jobs[name] = {"step": "Initializing", "status": "⟳ Running", "path": work_path, "session": session_name}
        kill_session(session_name)
        session = server.new_session(session_name, window_command="bash", attach=False, start_directory=str(job_dir.parent.absolute()))
        pane = session.windows[0].panes[0]
        # Setup commands
        setup_cmds = ["set -e", f"mkdir -p {job_dir.name}"]
        if repo:
            with jobs_lock: jobs[name] = {"step": f"Worktree: {work_path}", "status": "⟳ Running", "path": work_path, "session": session_name}
            setup_cmds.extend([f"cd {repo}", f"git worktree add --detach {work_path} {branch}", f"cd {work_path}"])
        else:
            setup_cmds.append(f"cd {job_dir.name}")
        # Send setup commands
        for cmd in setup_cmds:
            pane.send_keys(cmd)
            sleep(0.1)
        # Execute each step in the tmux session
        for i, step in enumerate(steps, 1):
            with jobs_lock: jobs[name] = {"step": f"{i}/{len(steps)}: {step['desc']}", "status": "⟳ Running", "path": work_path, "session": session_name}
            pane.send_keys(step["cmd"])
            sleep(0.2)  # Brief delay to ensure command is registered
        # Send marker command to detect completion
        marker = f"echo '__AIOS_COMPLETE_{name}_{ts}__'; echo $? > /tmp/aios-exit-{name}-{ts}"
        pane.send_keys(marker)
        # Monitor for completion (non-blocking)
        max_wait, interval = 300, 0.5  # 5 minute timeout
        for _ in range(int(max_wait / interval)):
            try:
                pane_content = pane.cmd('capture-pane', '-p').stdout
                if f'__AIOS_COMPLETE_{name}_{ts}__' in pane_content:
                    # Check exit status
                    exit_file = Path(f"/tmp/aios-exit-{name}-{ts}")
                    if exit_file.exists():
                        exit_code = int(exit_file.read_text().strip())
                        exit_file.unlink()
                        if exit_code == 0:
                            with jobs_lock: jobs[name] = {"step": f"✓ {job_dir.name}", "status": "✓ Done", "path": work_path, "session": session_name}
                            cleanup_old_jobs()
                        else:
                            with jobs_lock: jobs[name] = {"step": f"✗ Exit {exit_code}", "status": "✗ Error", "path": work_path, "session": session_name}
                        return
            except: pass
            sleep(interval)
        # Timeout
        with jobs_lock: jobs[name] = {"step": "Monitoring timeout", "status": "⟳ Running", "path": work_path, "session": session_name}
    except Exception as e:
        with jobs_lock: jobs[name] = {"step": str(e)[:50], "status": "✗ Error", "path": work_path, "session": session_name if 'session_name' in locals() else None}

def show_task_menu():
    tasks_dir = Path("tasks")
    if not tasks_dir.exists() or not (task_files := sorted(tasks_dir.glob("*.json"))): return []
    sep = "="*80
    print(f"\n{sep}\nWORKFLOWS\n{sep}")
    tasks = []
    for i, fp in enumerate(task_files, 1):
        try:
            task = json.loads(fp.read_text())
            tasks.append((fp, task))
            wt, var = '✓' if task.get('repo') else ' ', '⚙' if extract_variables(task) else ' '
            print(f"\n  {i}. [{wt}] [{var}] {task.get('name', fp.stem)}")
            for j, step in enumerate((steps := task.get('steps', []))[:5], 1):
                print(f"      {j}. {step.get('desc', 'No description')[:50]}")
            if len(steps) > 5: print(f"      ... +{len(steps)-5} more")
            if vars := extract_variables(task):
                defs = task.get('variables', {})
                print(f"      Vars: {', '.join(sorted(vars))}")
                if defs: print(f"      Defaults: {len(defs)}")
        except: pass
    with processed_files_lock:
        for fp, _ in tasks: processed_files.add(fp)
    print(f"\n{sep}\n[✓]=Worktree [⚙]=Variables\n{sep}\nSelect: '1 3 5' or 'all' or Enter to skip\n{sep}")
    if not (sel := input(">> ").strip()): return []
    selected = [t for _, t in tasks] if sel.lower() == 'all' else [tasks[i][1] for i in [int(p)-1 for p in sel.replace(',', ' ').split() if p.isdigit()] if 0 <= i < len(tasks)]
    return [pt for task in selected if (pt := prompt_for_variables(task))]

# Websocket PTY server for WEB INTERFACE ONLY
# NOTE: This is purely an endpoint for browser-based terminal access.
# For debugging and interactive work, LLMs and developers should use LOCAL terminal attach (press job # in TUI)
# which gives full native terminal control. Only use web interface (a #) when explicitly requested.
def get_or_create_web_terminal(session_name):
    """Create PTY that attaches to tmux session for WEB BROWSER access only

    This creates a separate PTY subprocess that attaches to the tmux session,
    allowing websocket clients to interact with it remotely. This is NOT for
    local terminal access - use direct tmux attach for that (see attach_local_terminal).
    """
    if session_name not in _terminal_sessions:
        # Create a new PTY pair
        master, slave = pty.openpty()
        # Set initial terminal size
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))

        # Check if tmux session exists
        if sess := get_session(session_name):
            # Fork and attach to existing tmux session in the PTY
            if (pid := os.fork()) == 0:
                os.setsid()
                [os.dup2(slave, fd) for fd in [0, 1, 2]]
                os.close(master)
                os.close(slave)
                # Attach to tmux session - tmux will detect PTY size automatically
                os.execvp('tmux', ['tmux', 'attach-session', '-t', session_name])
            os.close(slave)
            os.set_blocking(master, False)
            _terminal_sessions[session_name] = {"master": master, "pid": pid}
            return master
        else:
            # No tmux session, create a new PTY with bash
            if (pid := os.fork()) == 0:
                os.setsid()
                [os.dup2(slave, fd) for fd in [0, 1, 2]]
                os.close(master)
                os.close(slave)
                os.execv('/bin/bash', ['bash'])
            os.close(slave)
            os.set_blocking(master, False)
            _terminal_sessions[session_name] = {"master": master, "pid": pid}
            return master
    return _terminal_sessions[session_name]["master"]

async def ws_pty_bridge(websocket, session_name):
    """Bridge websocket to PTY for web browser terminal access"""
    master, loop = get_or_create_web_terminal(session_name), asyncio.get_event_loop()
    if master is None:
        await websocket.close()
        return
    def read_and_send():
        try:
            if data := os.read(master, 65536): asyncio.create_task(websocket.send(data))
        except: pass
    try:
        loop.add_reader(master, read_and_send)
        async for msg in websocket:
            if isinstance(msg, bytes):
                if msg[0:1] == b'{':
                    try:
                        d = json.loads(msg.decode())
                        if 'resize' in d:
                            rows, cols = d['resize']['rows'], d['resize']['cols']
                            # Resize the PTY - tmux will automatically detect and adjust
                            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
                            continue
                    except: pass
                os.write(master, msg)
    finally:
        try: loop.remove_reader(master)
        except: pass

# HTTP/WS servers
class TerminalHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        if path == "/terminal.html" and (html_file := Path("terminal.html")).exists():
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html_file.read_bytes())
            return
        self.send_response(404)
        self.end_headers()
    def log_message(self, *args): pass

class ReuseHTTPServer(HTTPServer):
    allow_reuse_address = True

http_server_thread = lambda: ReuseHTTPServer(('localhost', ws_port), TerminalHTTPHandler).serve_forever()

async def ws_handler(websocket):
    if (path := websocket.request.path).startswith("/attach/"):
        await ws_pty_bridge(websocket, path[8:])

def ws_server_thread():
    global ws_server_running
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def serve():
        global ws_server_running
        async with websockets.serve(ws_handler, "localhost", ws_port + 1):
            ws_server_running = True
            await asyncio.Future()
    try: loop.run_until_complete(serve())
    except: ws_server_running = False

def start_ws_server():
    global ws_server_running
    if not ws_server_running:
        Thread(target=http_server_thread, daemon=True).start()
        Thread(target=ws_server_thread, daemon=True).start()
        sleep(1)

get_job_session_name = lambda job_name: next((sess.name for sess in server.sessions if sess.name.startswith(f"aios-{job_name}-")), None)

def open_in_editor(job_name):
    """Open job directory in configured editor"""
    with jobs_lock:
        if job_name not in jobs:
            return f"✗ No job found: '{job_name}'"
        job_path = jobs[job_name].get("path")
        if not job_path:
            return f"✗ No path found for job '{job_name}'"
    editor_cmd = config.get("editor_command", "code .")
    try:
        subprocess.Popen(editor_cmd.split() + [job_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"✓ Opening '{job_name}' in editor: {job_path}"
    except Exception as e:
        return f"✗ Failed to open editor: {e}"

def open_terminal(job_name):
    if not (session_name := get_job_session_name(job_name)):
        return f"✗ No session found for job '{job_name}'"
    start_ws_server()
    url = f"http://localhost:{ws_port}/terminal.html?session={session_name}"
    Path("terminal.html").write_text(f'''<!DOCTYPE html>
<html><head><title>AIOS Terminal - {{job_name}}</title>
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css"/>
<style>
body {{
    margin: 0;
    padding: 0;
    background: #000;
    overflow: hidden;
}}
#terminal {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
}}
</style>
</head><body>
<div id="terminal"></div>
<script>
const term = new Terminal({{
    cursorBlink: true,
    fontSize: 14,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    theme: {{
        background: '#000000',
        foreground: '#ffffff'
    }},
    scrollback: 10000,
    convertEol: true
}});
const fitAddon = new FitAddon.FitAddon();
term.loadAddon(fitAddon);
term.open(document.getElementById('terminal'));
fitAddon.fit();

const params = new URLSearchParams(window.location.search);
const session = params.get('session');
const ws = new WebSocket('ws://localhost:{ws_port + 1}/attach/' + session);
ws.binaryType = 'arraybuffer';

ws.onopen = () => {{
    fitAddon.fit();
    const {{ cols, rows }} = term;
    ws.send(JSON.stringify({{ resize: {{ cols, rows }} }}));
}};

ws.onmessage = e => {{
    term.write(new Uint8Array(e.data));
}};

term.onData(data => {{
    ws.send(new TextEncoder().encode(data));
}});

window.addEventListener('resize', () => {{
    fitAddon.fit();
    const {{ cols, rows }} = term;
    ws.send(JSON.stringify({{ resize: {{ cols, rows }} }}));
}});

// Initial resize after a short delay to ensure proper sizing
setTimeout(() => {{
    fitAddon.fit();
    const {{ cols, rows }} = term;
    ws.send(JSON.stringify({{ resize: {{ cols, rows }} }}));
}}, 100);
</script>
</body></html>''')
    try:
        webbrowser.open(url)
        return f"✓ Opening web terminal for '{job_name}' at {url}"
    except:
        return f"✓ Web terminal available at {url} (open manually)"

def attach_local_terminal(job_name):
    """Attach to job's tmux session in current terminal - PREFERRED method for debugging

    This directly attaches the current terminal to the tmux session, giving full
    native terminal control. This is the PRIMARY way to interact with jobs.
    Use web terminal (open_terminal) only when browser access is explicitly needed.
    """
    if not (session_name := get_job_session_name(job_name)):
        return ("error", f"✗ No session found for job '{job_name}'")
    # Return signal to exit TUI and attach
    return ("attach_tmux", session_name, job_name)

# TUI mode
@timed
def get_status_text():
    sep = "=" * 80
    lines = [("class:header", f"{sep}\nAIOS - Running Tasks\n{sep}\n"), ("class:label", "\nJobs:"), ("class:help", " (Press # to watch job live)\n"), ("class:separator", "-" * 80 + "\n")]
    with jobs_lock:
        if jobs:
            for i, (jn, info) in enumerate(sorted(jobs.items()), 1):
                st, step = info["status"], info["step"][:45]
                style = "class:success" if "✓" in st else "class:error" if "✗" in st else "class:running"
                lines.extend([("class:text", f"  {i}. {jn:13} | {step:45} | "), (style, f"{st}\n")])
                if "path" in info:
                    lines.append(("class:dim", f"     → {info['path']}\n"))
        else:
            lines.append(("class:dim", "  (none)\n"))
    lines.extend([("class:label", "\nTodos:\n"), ("class:separator", "-" * 80 + "\n")])
    with todos_lock:
        if todos:
            for todo_id, todo in sorted(todos.items(), key=lambda x: x[1]['real_deadline']):
                title, rd = todo['title'][:40], todo['real_deadline']
                style, countdown = get_urgency_style(rd)
                lines.extend([("class:text", f"  {todo_id}. {title:40} | "), (style, f"{countdown}\n")])
        else:
            lines.append(("class:dim", "  (none)\n"))
    lines.extend([("class:label", "\nBuilder:\n"), ("class:separator", "-" * 80 + "\n")])
    with builder_lock:
        if task_builder:
            for jn, steps in sorted(task_builder.items()):
                lines.append(("class:text", f"  {jn}:\n"))
                [lines.append(("class:text", f"    {i}. {s['desc'][:70]}\n")) for i, s in enumerate(steps, 1)]
        else:
            lines.append(("class:dim", "  (none)\n"))
    lines.extend([("class:separator", f"\n{sep}\n"), ("class:help", "# "), ("class:help", "(watch)  "), ("class:command", "m"), ("class:help", " (menu)  "), ("class:command", "o #"), ("class:help", " (editor)  "), ("class:command", "a #"), ("class:help", " (browser)  "), ("class:command", "r <job>"), ("class:help", " (run)  "), ("class:command", "c <job>"), ("class:help", " (clear)  "), ("class:command", "q"), ("class:help", " (quit)"), ("class:separator", f"\n{sep}\n\n")])
    return FormattedText(lines)

def get_job_by_number(num):
    with jobs_lock:
        job_names = sorted(jobs.keys())
        if 1 <= num <= len(job_names): return job_names[num - 1]
    return None

@timed
def parse_and_route_command(cmd):
    global running
    if not cmd: return None
    if cmd in ["q", "quit"]:
        running = False
        return ("quit", None)
    if cmd in ["m", "menu"]: return ("menu", None)
    # Single number: attach to local terminal
    if cmd.isdigit():
        return ("local", job_name) if (job_name := get_job_by_number(int(cmd))) else ("local_error", f"No job #{cmd}")
    parts = cmd.split(None, 1)
    if len(parts) == 2:
        action, arg = parts
        if action in ["r", "run"]: return ("run", arg)
        if action in ["a", "attach"]:
            if arg.isdigit():
                return ("attach", job_name) if (job_name := get_job_by_number(int(arg))) else ("attach_error", f"No job #{arg}")
            return ("attach", arg)
        if action in ["l", "local"]:
            if arg.isdigit():
                return ("local", job_name) if (job_name := get_job_by_number(int(arg))) else ("local_error", f"No job #{arg}")
            return ("local", arg)
        if action in ["o", "open"]:
            if arg.isdigit():
                return ("open", job_name) if (job_name := get_job_by_number(int(arg))) else ("open_error", f"No job #{arg}")
            return ("open", arg)
        if action in ["c", "clear"]: return ("clear", arg)
        if action == "t":
            if arg[0] == '+':
                parts = arg[1:].split()
                if len(parts) >= 3 and is_deadline(parts[-1]) and is_deadline(parts[-2]):
                    return ("todo_add", {"title": ' '.join(parts[:-2]), "rd": parse_deadline(parts[-2]), "vd": parse_deadline(parts[-1])})
                elif len(parts) >= 2 and is_deadline(parts[-1]):
                    return ("todo_add", {"title": ' '.join(parts[:-1]), "rd": parse_deadline(parts[-1]), "vd": None})
            elif arg[0] == '✓': return ("todo_complete", int(arg[1:]))
            elif arg[0] == '✗': return ("todo_delete", int(arg[1:]))
    if " | " in cmd and ":" in (left := cmd.split(" | ", 1)[0]):
        jn, desc = left.split(":", 1)
        return ("build", {"job": jn.strip(), "desc": desc.strip(), "cmd": cmd.split(" | ", 1)[1].strip()})
    return ("unknown", None)

def process_command(cmd):
    if not (cmd := cmd.strip()): return None
    action, data = parse_and_route_command(cmd)
    if action == "quit": return "Shutting down..."
    if action == "menu": return "__SHOW_MENU__"
    if action == "run":
        with builder_lock:
            if data in task_builder:
                task_queue.put({"name": data, "steps": task_builder[data].copy()})
                del task_builder[data]
                return f"✓ Queued: {data}"
            return f"✗ Not found: {data}"
    if action == "attach": return open_terminal(data)
    if action == "attach_error": return data
    if action == "local":
        result = attach_local_terminal(data)
        if isinstance(result, tuple) and result[0] == "attach_tmux":
            return result  # Return signal to exit TUI and attach
        return result[1] if isinstance(result, tuple) else result
    if action == "local_error": return data
    if action == "open": return open_in_editor(data)
    if action == "open_error": return data
    if action == "clear":
        with builder_lock:
            if data in task_builder:
                del task_builder[data]
                return f"✓ Cleared: {data}"
            return f"✗ Not found: {data}"
    if action == "build":
        with builder_lock:
            if data["job"] not in task_builder: task_builder[data["job"]] = []
            task_builder[data["job"]].append({"desc": data["desc"], "cmd": data["cmd"]})
        return f"✓ Added to {data['job']}"
    if action == "todo_add":
        return f"✓ Added todo #{add_todo(data['title'], data['rd'], data['vd'])}"
    if action == "todo_complete":
        complete_todo(data)
        return f"✓ Completed todo #{data}"
    if action == "todo_delete":
        delete_todo(data)
        return f"✓ Deleted todo #{data}"
    return "✗ Unknown command"

def worker():
    """Worker thread that processes tasks from queue"""
    while running:
        try:
            task = task_queue.get(timeout=0.5)
            execute_task(task)
            task_queue.task_done()
        except Empty:
            continue
        except:
            break

# Event-based file watcher (no polling)
class TaskFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.json'):
            self.process_task_file(Path(event.src_path))
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.json'):
            self.process_task_file(Path(event.src_path))
    def process_task_file(self, json_file):
        with processed_files_lock:
            if json_file in processed_files: return
            processed_files.add(json_file)
        try:
            task = json.loads(json_file.read_text())
            if not extract_variables(task): task_queue.put(task)
        except: pass

def watch_folder():
    tasks_dir = Path("tasks")
    tasks_dir.mkdir(exist_ok=True)
    observer = Observer()
    observer.schedule(TaskFileHandler(), str(tasks_dir), recursive=False)
    observer.start()
    try:
        while running: sleep(1)
    finally:
        observer.stop()
        observer.join()

def run_tui_mode(selected_tasks):
    global running
    init_db()
    load_todos()
    for t in selected_tasks:
        task_queue.put(t)
        print(f"✓ Queued: {t['name']}")
    [Thread(target=worker, daemon=True).start() for _ in range(4)]
    Thread(target=watch_folder, daemon=True).start()
    Thread(target=notification_worker, daemon=True).start()
    show_menu_flag, attach_tmux_info = False, None
    while running:
        status_control = FormattedTextControl(text=get_status_text, focusable=False)
        status_window = Window(content=status_control, dont_extend_height=True)
        input_field = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)
        output_field = TextArea(height=3, focusable=False, scrollbar=False, read_only=True, text="")
        container = HSplit([status_window, output_field, input_field])
        kb = KeyBindings()
        @kb.add('enter')
        def _(event):
            nonlocal show_menu_flag, attach_tmux_info
            global running
            text, input_field.text = input_field.text, ""
            lines = text.split('\n') if '\n' in text else [text]
            results = []
            for line in lines:
                if (cmd := line.strip()) and (r := process_command(cmd)):
                    if r == "__SHOW_MENU__":
                        show_menu_flag = True
                        event.app.exit()
                        return
                    # Handle local terminal attach signal
                    if isinstance(r, tuple) and r[0] == "attach_tmux":
                        attach_tmux_info = r
                        event.app.exit()
                        return
                    results.append(r if isinstance(r, str) else str(r))
            if results: output_field.text = '\n'.join(results) if len(results) > 1 else results[0]
            if not running: event.app.exit()
        @kb.add('c-c')
        def _(event):
            global running
            running = False
            event.app.exit()
        style = Style.from_dict({'header': '#ff00ff bold', 'label': '#00ffff bold', 'separator': '#888888', 'text': '#ffffff', 'dim': '#666666', 'success': '#00ff00 bold', 'error': '#ff0000 bold', 'running': '#ffff00 bold', 'help': '#888888', 'command': '#00ffff'})
        app = Application(layout=Layout(container), key_bindings=kb, full_screen=True, style=style, mouse_support=False)
        def update_status():
            while running:
                sleep(0.5)
                try: app.invalidate()
                except: break
        Thread(target=update_status, daemon=True).start()
        try: app.run()
        except KeyboardInterrupt:
            running = False
            break
        # Handle local terminal attach - exit TUI, attach to tmux, return to TUI on detach
        if attach_tmux_info:
            _, session_name, job_name = attach_tmux_info
            attach_tmux_info = None
            print(f"\n✓ Attaching to '{job_name}' session: {session_name}")
            print("  (Press Ctrl+B then D to detach and return to AIOS)\n")
            sleep(1)
            try:
                # Direct tmux attach in current terminal - gives FULL interactive control
                subprocess.run(['tmux', 'attach-session', '-t', session_name])
                print(f"\n✓ Detached from '{job_name}'. Returning to AIOS TUI...\n")
                sleep(1)
            except Exception as e:
                print(f"\n✗ Failed to attach: {e}\n")
                sleep(2)
            if not running: break
            continue
        if show_menu_flag:
            show_menu_flag = False
            if tasks := show_task_menu():
                for t in tasks: task_queue.put(t)
                print(f"\n✓ Queued {len(tasks)} task(s). Returning to TUI...\n")
                sleep(1)
            else:
                print("\nNo tasks selected. Returning to TUI...\n")
                sleep(1)
            if not running: break
        else:
            break
    print("\nShutdown complete.")

# Simple mode
def run_simple_mode(selected_tasks):
    init_db()
    load_todos()
    if not selected_tasks: return print("No tasks selected")
    print(f"\nStarting {len(selected_tasks)} task(s)...")
    threads = [Thread(target=execute_task, args=(t,)) for t in selected_tasks]
    [t.start() for t in threads]
    [t.join() for t in threads]
    sep = "="*80
    with jobs_lock:
        print(f"\n{sep}")
        [print(f"{n}: {info['status']} | {info['step']}") for n, info in jobs.items()]
        print(sep)
    print("\n✓ All tasks complete!")

# Self-update mechanism (git-style with automatic HTTPS fallback)
def self_update(silent=False, auto=False):
    """Update AIOS to latest version from git
    silent: Don't print status messages
    auto: Auto-install without confirmation

    Automatically falls back to HTTPS if SSH authentication fails
    """
    if not silent: print("Checking for updates...")
    try:
        install_dir = Path(__file__).parent
        # Environment to disable all interactive prompts
        git_env = os.environ.copy()
        git_env['GIT_TERMINAL_PROMPT'] = '0'  # Disable terminal prompts
        git_env['GIT_ASKPASS'] = 'echo'  # Disable password prompts
        git_env['SSH_ASKPASS'] = 'echo'  # Disable SSH password prompts
        git_env['GIT_SSH_COMMAND'] = 'ssh -oBatchMode=yes'  # Disable SSH interactive auth

        # Check if we're in a git repo (with timeout, no prompts)
        result = subprocess.run(['git', '-C', str(install_dir), 'rev-parse', '--git-dir'],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env=git_env, timeout=5)
        if result.returncode != 0:
            if not silent: print("✗ Not installed from git repository. Use: pip install --upgrade aios-cli")
            return 1

        # Check current remote URL
        result = subprocess.run(['git', '-C', str(install_dir), 'remote', 'get-url', 'origin'],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env=git_env, timeout=5)
        remote_url = result.stdout.strip() if result.returncode == 0 else ""
        is_ssh = remote_url.startswith('git@') or remote_url.startswith('ssh://')

        # Fetch latest changes (with timeout, no prompts)
        if not silent: print("Fetching latest version...")
        result = subprocess.run(['git', '-C', str(install_dir), 'fetch', 'origin'],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env=git_env, timeout=10)

        # If SSH fetch fails, automatically try HTTPS fallback
        if result.returncode != 0 and is_ssh and auto:
            # Convert SSH URL to HTTPS (supports GitHub, GitLab, Bitbucket, etc.)
            https_url = remote_url
            # Format: git@host:user/repo.git → https://host/user/repo.git
            if '@' in https_url and ':' in https_url:
                parts = https_url.split('@')[1].split(':')
                if len(parts) == 2:
                    https_url = f"https://{parts[0]}/{parts[1]}"
            # Format: ssh://git@host/user/repo.git → https://host/user/repo.git
            https_url = https_url.replace('ssh://git@', 'https://')

            if https_url != remote_url and https_url.startswith('https://'):
                # Permanently switch to HTTPS remote and retry fetch
                subprocess.run(['git', '-C', str(install_dir), 'remote', 'set-url', 'origin', https_url],
                             capture_output=True, stdin=subprocess.DEVNULL, env=git_env, timeout=5)
                result = subprocess.run(['git', '-C', str(install_dir), 'fetch', 'origin'],
                                      capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                      env=git_env, timeout=10)
                if result.returncode == 0:
                    if not silent: print(f"✓ Auto-switched to HTTPS: {https_url}")
                    # Configure git to cache credentials for 1 week
                    subprocess.run(['git', '-C', str(install_dir), 'config', 'credential.helper', 'cache --timeout=604800'],
                                 capture_output=True, stdin=subprocess.DEVNULL, env=git_env, timeout=5)

        if result.returncode != 0:
            # If fetch fails, skip silently in auto mode
            if not silent: print("✗ Unable to fetch updates (check network connection)")
            return 1

        # Check if updates available
        result = subprocess.run(['git', '-C', str(install_dir), 'rev-list', 'HEAD..origin/main', '--count'],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env=git_env, timeout=5)
        if result.returncode != 0 or not result.stdout.strip():
            if not silent: print("✓ Already up to date")
            return 0
        commits_behind = int(result.stdout.strip())
        if commits_behind == 0:
            if not silent: print("✓ Already up to date")
            return 0

        if not silent:
            print(f"Updates available ({commits_behind} commit{'s' if commits_behind > 1 else ''} behind)")
            result = subprocess.run(['git', '-C', str(install_dir), 'log', '--oneline', 'HEAD..origin/main'],
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  env=git_env, timeout=5)
            print(f"\nChanges:\n{result.stdout}")

        # Confirm update (skip if auto)
        if not auto:
            if input("\nUpdate now? [Y/n]: ").strip().lower() not in ['', 'y', 'yes']:
                print("Update cancelled")
                return 0

        # Pull latest changes
        if not silent: print("\nUpdating...")
        result = subprocess.run(['git', '-C', str(install_dir), 'pull', 'origin', 'main'],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env=git_env, timeout=15)
        if result.returncode != 0:
            if not silent: print(f"✗ Pull failed: {result.stderr}")
            return 1

        # Reinstall if installed via pip
        try:
            subprocess.run(['pip', 'install', '-e', str(install_dir)],
                         check=True, capture_output=True, stdin=subprocess.DEVNULL, timeout=30)
            if not silent: print("✓ AIOS updated successfully")
        except:
            if not silent: print("✓ AIOS updated (restart your terminal if using pip install -e)")
        return 0
    except subprocess.TimeoutExpired:
        if not silent: print("✗ Update check timed out")
        return 1
    except subprocess.CalledProcessError as e:
        if not silent: print(f"✗ Update failed: {e}")
        return 1
    except Exception as e:
        if not silent: print(f"✗ Error: {e}")
        return 1

def auto_update_check():
    """Background auto-update check (non-blocking, cached)"""
    if not config.get("auto_update", False): return
    now = int(time())
    last_check = config.get("last_update_check", 0)
    check_interval = config.get("check_interval", 86400)
    if now - last_check < check_interval: return  # Don't check too frequently
    def background_update():
        try:
            result = self_update(silent=True, auto=True)
            if result == 0:
                config["last_update_check"] = int(time())
                save_config(config)
        except: pass  # Silent failure
    Thread(target=background_update, daemon=True).start()

# Test mode
def run_tests():
    print("="*80 + "\nAIOS Built-in Tests\n" + "="*80 + "\n")
    failed = []
    # Test 0: AIOS overhead functions
    print("0. Testing AIOS overhead functions...")
    try:
        task = {"name": "test", "steps": [{"desc": "{{action}}", "cmd": "echo {{message}}"}]}
        vars = extract_variables(task)
        if "action" not in vars or "message" not in vars: raise Exception("Variable extraction failed")
        sub = substitute_variables(task, {"action": "run", "message": "world"})
        if "run" not in str(sub) or "world" not in str(sub): raise Exception("Variable substitution failed")
        status = get_status_text()
        if len(status) < 5: raise Exception("Status rendering failed")
        for cmd in ["q", "m", "r test", "a job", "c job", "a 1"]:
            if not parse_and_route_command(cmd): raise Exception(f"Command parsing failed: {cmd}")
        print(f"   ✓ All overhead functions working")
        print(f"   ✓ Timings: extract={timings_current.get('extract_variables',0)*1000:.2f}ms, substitute={timings_current.get('substitute_variables',0)*1000:.2f}ms, parse={timings_current.get('parse_and_route_command',0)*1000:.2f}ms, render={timings_current.get('get_status_text',0)*1000:.2f}ms")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        failed.append("AIOS overhead")
    print()
    # Test 1: PTY terminal
    print("1. Testing PTY terminal creation...")
    try:
        test_session = server.new_session("test-aios-pty", window_command="bash", attach=False)
        sleep(1)
        master = get_or_create_web_terminal("test-aios-pty")
        if master < 0: raise Exception("Invalid master fd")
        os.write(master, b"echo TEST_PTY_OK\n")
        sleep(0.5)
        os.set_blocking(master, False)
        output = b""
        try:
            for _ in range(5): output += os.read(master, 4096)
        except BlockingIOError: pass
        if b"TEST_PTY_OK" not in output: raise Exception("PTY output not received")
        print("   ✓ PTY creation and I/O working")
        test_session.kill()
        del _terminal_sessions["test-aios-pty"]
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        failed.append("PTY terminal creation")
    # Test 2: WebSocket server
    print("\n2. Testing WebSocket server...")
    try:
        test_session = server.new_session("test-aios-ws", window_command="bash", attach=False)
        sleep(1)
        start_ws_server()
        sleep(2)
        if not ws_server_running: raise Exception("WebSocket server not running")
        print(f"   ✓ Servers started (HTTP:{ws_port}, WS:{ws_port + 1})")
        async def test_ws():
            try:
                uri = f"ws://localhost:{ws_port + 1}/attach/test-aios-ws"
                async with websockets.connect(uri) as ws:
                    await ws.send(b"echo WS_TEST\n")
                    for _ in range(10):
                        try:
                            if b"WS_TEST" in (msg := await asyncio.wait_for(ws.recv(), timeout=1.0)): return True
                        except asyncio.TimeoutError: continue
            except Exception as e: raise Exception(f"WebSocket connection failed: {e}")
            return False
        if not asyncio.run(test_ws()): raise Exception("WebSocket test failed")
        print("   ✓ WebSocket connection and communication working")
        test_session.kill()
        if "test-aios-ws" in _terminal_sessions: del _terminal_sessions["test-aios-ws"]
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        failed.append("WebSocket server")
    # Test 3: HTTP server
    print("\n3. Testing HTTP server...")
    try:
        html_file = Path("terminal.html")
        html_file.write_text("<html><body>TEST_HTML</body></html>")
        response = urllib.request.urlopen(f"http://localhost:{ws_port}/terminal.html?session=test", timeout=5)
        if "TEST_HTML" not in (content := response.read().decode()): raise Exception("HTTP server returned unexpected content")
        print("   ✓ HTTP server serving with query strings")
        html_file.unlink()
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        failed.append("HTTP server")
    # Summary
    print("\n" + "="*80)
    if not failed:
        print("✓ ALL TESTS PASSED\n" + "="*80)
        return 0
    else:
        print(f"✗ {len(failed)} TEST(S) FAILED")
        [print(f"  - {test}") for test in failed]
        print("="*80)
        return 1

def get_git_info():
    """Get current git repo path and branch"""
    try:
        result = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=2)
        repo_path = result.stdout.strip() if result.returncode == 0 else str(Path.cwd())
        result = subprocess.run(['git', 'branch', '--show-current'], capture_output=True, text=True, timeout=2)
        branch_name = result.stdout.strip() if result.returncode == 0 else 'main'
        return repo_path, branch_name
    except:
        return str(Path.cwd()), 'main'

def list_workflows():
    """List available workflows"""
    tasks_dir = Path("tasks")
    if not tasks_dir.exists(): return []
    workflows = []
    for fp in sorted(tasks_dir.glob("*.json")):
        try:
            workflows.append((fp, json.loads(fp.read_text())))
        except: pass
    return workflows

def select_workflow_interactive(prompt_text):
    """Interactive workflow selector with codex as default"""
    workflows = list_workflows()
    if not workflows:
        print("✗ No workflows found in tasks/")
        return None
    sep = "="*80
    print(f"\n{sep}\nSELECT WORKFLOW\n{sep}")
    # Prefer workflows with variables (dynamic prompts), then 'codex' in name, then first
    default_idx = None
    for i, (fp, task) in enumerate(workflows, 1):
        if extract_variables(task) and default_idx is None:
            default_idx = i
    if default_idx is None:
        for i, (fp, task) in enumerate(workflows, 1):
            if 'codex' in fp.stem.lower() and default_idx is None: default_idx = i
    for i, (fp, task) in enumerate(workflows, 1):
        marker = ' [DEFAULT]' if i == default_idx else ''
        wt, var = '✓' if task.get('repo') else ' ', '⚙' if extract_variables(task) else ' '
        print(f"  {i}. [{wt}] [{var}] {task.get('name', fp.stem)}{marker}")
    print(f"{sep}")
    try:
        selection = input(f"Select workflow [1-{len(workflows)}] (default={default_idx or 1}): ").strip()
    except EOFError:
        selection = ""  # Use default when stdin is not available
    if not selection: selection = str(default_idx or 1)
    try:
        idx = int(selection) - 1
        if 0 <= idx < len(workflows): return workflows[idx]
    except: pass
    return None

def create_prompt_task(workflow_fp, workflow_task, user_prompt):
    """Create task from workflow with auto-filled variables"""
    repo_path, branch_name = get_git_info()
    full_prompt = f"{user_prompt}\n\n{CODING_STANDARDS}"
    auto_vars = {
        'task_description': full_prompt,
        'dynamic_prompt': full_prompt,
        'repo_path': repo_path,
        'branch_name': branch_name
    }
    defaults = workflow_task.get('variables', {})
    defaults.update(auto_vars)

    while True:
        task_copy = json.loads(json.dumps(workflow_task))
        task_copy['variables'] = defaults
        # Substitute variables to show exact commands
        task_substituted = substitute_variables(task_copy, defaults)
        sep = "="*80
        print(f"\n{sep}\nPROMPT PREVIEW\n{sep}")
        print(f"Workflow: {workflow_task.get('name', workflow_fp.stem)}")
        print(f"Repo: {repo_path}")
        print(f"Branch: {branch_name}")
        # Only show user prompt if workflow uses it
        workflow_vars = extract_variables(workflow_task)
        if 'task_description' in workflow_vars or 'dynamic_prompt' in workflow_vars:
            print(f"\nYour prompt:\n{user_prompt}")
        print(f"\n{sep}\nCOMMANDS (with variables substituted)\n{sep}")
        for i, step in enumerate(task_substituted.get('steps', []), 1):
            desc = step.get('desc', 'No description')
            cmd = step.get('cmd', '')
            print(f"  {i}. {desc}")
            print(f"     $ {cmd}")
        print(f"{sep}")
        try:
            confirm = input("Execute? [Y/n/e=edit]: ").strip().lower()
        except EOFError:
            confirm = ""  # Use default (yes) when stdin is not available

        if confirm in ['', 'y', 'yes']:
            return substitute_variables(task_copy, defaults)
        elif confirm in ['e', 'edit']:
            print(f"\n{sep}\nEDIT VARIABLES\n{sep}")
            print("Leave blank to keep current value")
            for k in sorted(auto_vars.keys()):
                current = str(defaults[k])
                preview = current[:40] + '...' if len(current) > 40 else current
                try:
                    new_val = input(f"{k} [{preview}]: ").strip()
                except EOFError:
                    new_val = ""  # Keep current value when stdin is not available
                if new_val: defaults[k] = new_val
        else:
            return None

def get_immediate_prompt():
    """Get prompt from args or stdin (for paste support)"""
    args = [a for a in sys.argv[1:] if not a.startswith('-') and not a.endswith('.json')]
    if args: return ' '.join(args)
    if not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
        try:
            sys.stdin = open('/dev/tty', 'r')  # Reopen stdin for subsequent input() calls
        except OSError:
            pass  # No controlling terminal available
        return prompt
    print("Enter your prompt (paste or type, then Ctrl+D):")
    return sys.stdin.read().strip()

def run_immediate_prompt_mode():
    """New mode: immediate prompt entry with workflow selection"""
    prompt_text = get_immediate_prompt()
    if not prompt_text:
        print("✗ No prompt provided")
        return []
    workflow = select_workflow_interactive(prompt_text)
    if not workflow:
        print("✗ No workflow selected")
        return []
    workflow_fp, workflow_task = workflow
    if task := create_prompt_task(workflow_fp, workflow_task, prompt_text):
        return [task]
    return []

def install():
    """Install AIOS globally"""
    pyproject = '''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "aios-cli"
version = "1.0.0"
description = "AIOS Task Manager - git-inspired CLI for task orchestration"
readme = "README.md"
requires-python = ">=3.9"
license = {text = "MIT"}
dependencies = [
    "libtmux>=0.21.0",
    "prompt-toolkit>=3.0.0",
    "websockets>=11.0",
    "watchdog>=3.0.0",
]

[project.scripts]
aios = "aios:main"

[tool.setuptools]
py-modules = ["aios"]
'''
    print("="*80)
    print("AIOS Installation")
    print("="*80)

    # Check Python version
    if sys.version_info < (3, 9):
        print("✗ Python 3.9+ required")
        return 1
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}")

    # Check pip
    try:
        subprocess.run(['pip', '--version'], capture_output=True, check=True)
        print("✓ pip installed")
    except:
        print("✗ pip not found")
        return 1

    # Check tmux
    try:
        subprocess.run(['tmux', '-V'], capture_output=True, check=True)
        print("✓ tmux installed")
    except:
        print("✗ tmux not found - install with: sudo apt install tmux")
        return 1

    # Write pyproject.toml
    pyproject_file = Path("pyproject.toml")
    pyproject_file.write_text(pyproject)
    print("✓ Created pyproject.toml")

    # Install with pip
    print("\nInstalling AIOS...")
    try:
        subprocess.run(['pip', 'install', '-e', '.', '--user'], check=True)
        print("\n" + "="*80)
        print("✓ AIOS installed successfully!")
        print("="*80)
        print("\nNext steps:")
        print("  1. Add to PATH: export PATH=\"$HOME/.local/bin:$PATH\"")
        print("  2. Enable auto-updates: aios --auto-update-on")
        print("  3. Run tests: aios --test")
        print("  4. Start using: aios")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Installation failed: {e}")
        return 1

def main():
    """Main entry point"""
    global config
    # Install mode
    if "--install" in sys.argv:
        sys.exit(install())
    # Auto-update configuration
    if "--auto-update-on" in sys.argv:
        config["auto_update"] = True
        save_config(config)
        print("✓ Auto-update enabled (checks once per day)")
        return
    if "--auto-update-off" in sys.argv:
        config["auto_update"] = False
        save_config(config)
        print("✓ Auto-update disabled")
        return
    # Self-update mode
    if "--update" in sys.argv:
        sys.exit(self_update(silent=False, auto=False))
    # Test mode
    if "--test" in sys.argv:
        sys.exit(run_tests())
    # Background auto-update check (non-blocking)
    auto_update_check()
    simple_mode = "--simple" in sys.argv or "-s" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ["--simple", "-s", "--profile", "--update", "--auto-update-on", "--auto-update-off", "--test"]]

    # Separate .json files from prompt text
    json_args = [a for a in args if a.endswith('.json')]

    if json_args:
        # Traditional mode: load .json files
        print("Loading AIOS...")
        selected_tasks = []
        for fp in json_args:
            try:
                task = json.loads(Path(fp).read_text())
                if task := prompt_for_variables(task):
                    selected_tasks.append(task)
                    print(f"✓ Loaded: {task['name']}")
            except Exception as e:
                print(f"✗ Error loading {fp}: {e}")
    else:
        # Immediate prompt mode (default)
        selected_tasks = run_immediate_prompt_mode()

    if simple_mode:
        run_simple_mode(selected_tasks)
    else:
        run_tui_mode(selected_tasks)
    if profile_mode and timings_current:
        save_timings(timings_current)
        print(f"\n✓ Saved {len(timings_current)} function timings to {TIMINGS_FILE}")

if __name__ == "__main__":
    main()
