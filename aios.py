#!/usr/bin/env python3
"""AIOS Task Manager - git-inspired design

Usage:
    aios.py [--profile] [--simple|-s] [--test] [task.json ...]

Modes:
    Default: Interactive TUI (running tasks view)
    --profile: Profile functions and save baseline timings
    --simple: Batch execution with simple monitoring
    --test: Run built-in tests

Examples:
    ./aios.py                    # TUI mode (running tasks default)
    ./aios.py --profile          # Profile and save timings
    ./aios.py task.json          # Load task, run in TUI
    ./aios.py --simple task.json # Batch mode
    ./aios.py --test             # Run tests

Commands in TUI:
    m          - Show workflow menu
    a <#|name> - Attach terminal to job (e.g., "a 1" or "a jobname")
    r <job>    - Run job from builder
    c <job>    - Clear job from builder
    q          - Quit
"""

import libtmux, json, sys, re, shutil, asyncio, websockets, webbrowser, subprocess, pty, fcntl, termios, struct, os, signal
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

# Global state
server, jobs, jobs_lock = libtmux.Server(), {}, Lock()
task_queue, task_builder, builder_lock = Queue(), {}, Lock()
running, processed_files, processed_files_lock = True, set(), Lock()
ws_port, ws_server_running = 7681, False
JOBS_DIR, MAX_JOB_DIRS = Path("jobs"), 20
_terminal_sessions = {}  # Persistent PTY terminals
TIMINGS_FILE, profile_mode = Path(".aios_timings.json"), "--profile" in sys.argv

# Performance enforcement: AIOS overhead ONLY (not user commands)
# TARGET: ≤0.5ms (500μs) - strict enforcement accounting for Python timing variance
def load_timings():
    return json.loads(TIMINGS_FILE.read_text()) if TIMINGS_FILE.exists() else {}

def save_timings(timings):
    TIMINGS_FILE.write_text(json.dumps(timings, indent=2))

timings_baseline = {} if profile_mode else load_timings()
timings_current = {}

def timed(func):
    """Decorator: Time AIOS overhead only. SIGKILL if > baseline + 0.5ms"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time()
        result = func(*args, **kwargs)
        elapsed = time() - start
        fname = func.__name__

        if profile_mode:
            timings_current[fname] = elapsed
        elif fname in timings_baseline:
            if elapsed > timings_baseline[fname] + 0.0005:  # 0.5ms tolerance
                baseline_ms = timings_baseline[fname] * 1000
                elapsed_ms = elapsed * 1000
                over_ms = (elapsed - timings_baseline[fname]) * 1000
                print(f"\n✗ PERF REGRESSION: {fname} {elapsed_ms:.2f}ms (baseline {baseline_ms:.2f}ms, +{over_ms:.2f}ms over)")
                os.kill(os.getpid(), signal.SIGKILL)
        return result
    return wrapper

# Core functions (plumbing - inspired by git's core)
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
    """NOTE: Not timed - includes user input time"""
    if not (variables := extract_variables(task)): return task
    defaults, sep = task.get('variables', {}), "="*80

    print(f"\n{sep}\nTEMPLATE PREVIEW\n{sep}\n{json.dumps(task, indent=2)}\n{sep}\n{sep}\nDEFAULTS\n{sep}")
    for var in sorted(variables):
        d = defaults.get(var, '(no default)')
        print(f"  {var}: {str(d)[:60]+'...' if len(str(d))>60 else d}")
    print(f"{sep}\n{sep}\nVARIABLES\n{sep}")

    # Collect variable values
    values = {}
    for var in sorted(variables):
        default = defaults.get(var, '')
        if default:
            short_default = str(default)[:30] + '...' if len(str(default)) > 30 else str(default)
            prompt_text = f"{var} [{short_default}]: "
        else:
            prompt_text = f"{var}: "
        user_input = input(prompt_text).strip()
        values[var] = user_input if user_input else default

    sub = substitute_variables(task, values)
    print(f"{sep}\n{sep}\nFINAL\n{sep}\n{json.dumps(sub, indent=2)}\n{sep}")

    return None if (c := input("Launch? [Y/n]: ").strip().lower()) and c not in ['y', 'yes'] else sub

def cleanup_old_jobs():
    """NOTE: Not timed - filesystem I/O (glob, stat, rmtree) varies with job count"""
    if JOBS_DIR.exists():
        for d in sorted(JOBS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[MAX_JOB_DIRS:]:
            try: shutil.rmtree(d)
            except: pass

def get_session(name): return next((s for s in server.sessions if s.name == name), None)
def kill_session(name):
    if (sess := get_session(name)): sess.kill()

def execute_task(task):
    """Event-driven execution - subprocess.run() blocks on completion, zero polling
    NOTE: Not timed - includes arbitrary user command execution time"""
    name, steps = task["name"], task["steps"]
    repo, branch = task.get("repo"), task.get("branch", "main")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"aios-{name}-{ts}"
    JOBS_DIR.mkdir(exist_ok=True)
    job_dir = JOBS_DIR / f"{name}-{ts}"
    worktree_dir = job_dir / "worktree" if repo else None

    try:
        with jobs_lock: jobs[name] = {"step": "Initializing", "status": "⟳ Running"}
        kill_session(session_name)

        # Create tmux session for display only
        session = server.new_session(session_name, window_command="bash --norc --noprofile", attach=False)

        # Build full command script (use job_dir.name since cwd will be parent)
        cmds = [f"set -e", f"mkdir -p {job_dir.name}"]

        if repo:
            work_dir = str(worktree_dir.absolute())
            with jobs_lock: jobs[name] = {"step": f"Worktree: {work_dir}", "status": "⟳ Running"}
            cmds.extend([f"cd {repo}", f"git worktree add --detach {work_dir} {branch}", f"cd {work_dir}"])
        else:
            work_dir = str(job_dir.absolute())
            cmds.append(f"cd {job_dir.name}")

        # Add all task steps
        for i, step in enumerate(steps, 1):
            with jobs_lock: jobs[name] = {"step": f"{i}/{len(steps)}: {step['desc']}", "status": "⟳ Running"}
            cmds.append(step["cmd"])

        # Execute via subprocess - blocks until complete (event-driven)
        script = "\n".join(cmds)
        result = subprocess.run(["bash", "-c", script], cwd=str(job_dir.parent.absolute()), capture_output=True, text=True, timeout=120)

        # Send output to tmux for display
        if session:
            pane = session.windows[0].panes[0]
            for line in (result.stdout + result.stderr).split('\n')[:50]:  # Last 50 lines
                pane.send_keys(line, literal=True)

        if result.returncode == 0:
            job_name = job_dir.name
            with jobs_lock: jobs[name] = {"step": f"✓ {job_name}", "status": "✓ Done"}
            cleanup_old_jobs()
        else:
            # Show first error line from stderr for context
            error_lines = result.stderr.strip().split('\n') if result.stderr else []
            error_msg = error_lines[-1][:60] if error_lines else f"Exit {result.returncode}"
            with jobs_lock: jobs[name] = {"step": f"✗ {error_msg}", "status": "✗ Error"}

    except subprocess.TimeoutExpired:
        with jobs_lock: jobs[name] = {"step": "Timeout", "status": "✗ Timeout"}
    except Exception as e:
        with jobs_lock: jobs[name] = {"step": str(e)[:50], "status": "✗ Error"}

def show_task_menu():
    """NOTE: Not timed - includes user input time"""
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

    print(f"\n{sep}\n[✓]=Worktree [⚙]=Variables\n{sep}")
    print("Select: '1 3 5' or 'all' or Enter to skip\n" + sep)

    if not (sel := input(">> ").strip()): return []

    # Parse selection
    if sel.lower() == 'all':
        selected = [t for _, t in tasks]
    else:
        indices = [int(p)-1 for p in sel.replace(',', ' ').split() if p.isdigit()]
        selected = [tasks[i][1] for i in indices if 0 <= i < len(tasks)]

    return [pt for task in selected if (pt := prompt_for_variables(task))]

# Websocket PTY server (inspired by git daemon) - event-driven with binary messages
def get_or_create_terminal(session_name):
    """Get or create persistent PTY terminal for session"""
    if session_name not in _terminal_sessions:
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))

        if (pid := os.fork()) == 0:  # Child process
            os.setsid()
            os.dup2(slave, 0)
            os.dup2(slave, 1)
            os.dup2(slave, 2)
            os.close(master)
            os.close(slave)

            # Get working directory from session name
            sess = get_session(session_name)
            if sess:
                try:
                    cwd = sess.windows[0].panes[0].current_path
                    os.chdir(cwd)
                except: pass

            os.execv('/bin/bash', ['bash'])

        os.close(slave)
        os.set_blocking(master, False)
        _terminal_sessions[session_name] = {"master": master, "pid": pid}

    return _terminal_sessions[session_name]["master"]

async def ws_pty_bridge(websocket, session_name):
    """Event-driven bridge: websocket<->PTY"""
    master = get_or_create_terminal(session_name)
    loop = asyncio.get_event_loop()

    def read_and_send():
        try:
            if data := os.read(master, 65536):
                asyncio.create_task(websocket.send(data))
        except: pass

    try:
        loop.add_reader(master, read_and_send)

        async for msg in websocket:
            if isinstance(msg, bytes):
                # Handle resize events
                if msg[0:1] == b'{':
                    try:
                        d = json.loads(msg.decode())
                        if 'resize' in d:
                            rows, cols = d['resize']['rows'], d['resize']['cols']
                            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
                            continue
                    except: pass
                os.write(master, msg)
    finally:
        try: loop.remove_reader(master)
        except: pass

# HTTP server for serving terminal.html (git daemon style - separate servers)
class TerminalHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Strip query string for path matching
        path = self.path.split('?')[0]
        if path == "/terminal.html":
            html_file = Path("terminal.html")
            if html_file.exists():
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

def http_server_thread():
    """HTTP server thread"""
    try:
        httpd = ReuseHTTPServer(('localhost', ws_port), TerminalHTTPHandler)
        httpd.serve_forever()
    except: pass

async def ws_handler(websocket):
    """Binary websocket handler for xterm.js"""
    path = websocket.request.path
    if path.startswith("/attach/"):
        await ws_pty_bridge(websocket, path[8:])

def ws_server_thread():
    """WebSocket server thread (separate port)"""
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
    """Start HTTP and WebSocket servers if not already running"""
    global ws_server_running
    if not ws_server_running:
        Thread(target=http_server_thread, daemon=True).start()
        Thread(target=ws_server_thread, daemon=True).start()
        sleep(1)  # Let servers start

def get_job_session_name(job_name):
    """Find tmux session name for a job"""
    # Search all tmux sessions (don't rely on jobs dict for cross-process)
    for sess in server.sessions:
        if sess.name.startswith(f"aios-{job_name}-"):
            return sess.name
    return None

def open_terminal(job_name):
    """Open web terminal for job"""
    session_name = get_job_session_name(job_name)
    if not session_name:
        return f"✗ No session found for job '{job_name}'"

    start_ws_server()
    url = f"http://localhost:{ws_port}/terminal.html?session={session_name}"

    # Create HTML terminal client with xterm.js (always regenerate to ensure latest)
    html_file = Path("terminal.html")
    html_file.write_text(f'''<!DOCTYPE html>
<html><head><title>AIOS Terminal</title>
<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit/lib/xterm-addon-fit.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css"/>
<style>body{{margin:0;background:#000}}#terminal{{height:100vh}}</style>
</head><body>
<div id="terminal"></div>
<script>
const term = new Terminal();
const fit = new FitAddon.FitAddon();
term.loadAddon(fit);
term.open(document.getElementById('terminal'));
fit.fit();
const params = new URLSearchParams(window.location.search);
const session = params.get('session');
const ws = new WebSocket('ws://localhost:{ws_port + 1}/attach/' + session);
ws.binaryType = 'arraybuffer';
ws.onmessage = e => term.write(new Uint8Array(e.data));
term.onData(d => ws.send(new TextEncoder().encode(d)));
window.onresize = () => fit.fit();
</script>
</body></html>''')

    try:
        webbrowser.open(url)
        return f"✓ Opening terminal for '{job_name}' at {url}"
    except:
        return f"✓ Terminal available at {url} (open manually)"

# TUI mode (porcelain - inspired by git's interactive commands)
@timed
def get_status_text():
    """AIOS overhead: UI rendering only"""
    sep = "=" * 80
    lines = [("class:header", f"{sep}\nAIOS - Running Tasks\n{sep}\n"),
             ("class:label", "\nJobs:\n"), ("class:separator", "-" * 80 + "\n")]

    with jobs_lock:
        if jobs:
            for i, (jn, info) in enumerate(sorted(jobs.items()), 1):
                st, step = info["status"], info["step"][:45]
                style = "class:success" if "✓" in st else "class:error" if "✗" in st else "class:running"
                lines.extend([("class:text", f"  {i}. {jn:13} | {step:45} | "), (style, f"{st}\n")])
        else:
            lines.append(("class:dim", "  (none)\n"))

    lines.extend([("class:label", "\nBuilder:\n"), ("class:separator", "-" * 80 + "\n")])
    with builder_lock:
        if task_builder:
            for jn, steps in sorted(task_builder.items()):
                lines.append(("class:text", f"  {jn}:\n"))
                for i, s in enumerate(steps, 1): lines.append(("class:text", f"    {i}. {s['desc'][:70]}\n"))
        else:
            lines.append(("class:dim", "  (none)\n"))

    lines.extend([("class:separator", f"\n{sep}\n"), ("class:help", "Commands: "),
                  ("class:command", "m"), ("class:help", " (menu)  "),
                  ("class:command", "a <#|name>"), ("class:help", " (attach terminal)  "),
                  ("class:command", "r <job>"), ("class:help", " (run)  "),
                  ("class:command", "c <job>"), ("class:help", " (clear)  "),
                  ("class:command", "q"), ("class:help", " (quit)"),
                  ("class:separator", f"\n{sep}\n\n")])
    return FormattedText(lines)

def get_job_by_number(num):
    """Get job name by display number (1-indexed)"""
    with jobs_lock:
        job_names = sorted(jobs.keys())
        if 1 <= num <= len(job_names):
            return job_names[num - 1]
    return None

@timed
def parse_and_route_command(cmd):
    """AIOS overhead: Command parsing and routing logic only"""
    global running
    if not cmd: return None
    if cmd in ["q", "quit"]:
        running = False
        return ("quit", None)
    if cmd in ["m", "menu"]:
        return ("menu", None)

    parts = cmd.split(None, 1)
    if len(parts) == 2:
        action, arg = parts
        if action in ["r", "run"]: return ("run", arg)
        if action in ["a", "attach"]:
            # Support numeric job reference (e.g., "a 1")
            if arg.isdigit():
                if job_name := get_job_by_number(int(arg)):
                    return ("attach", job_name)
                return ("attach_error", f"No job #{arg}")
            return ("attach", arg)
        if action in ["c", "clear"]: return ("clear", arg)

    if " | " in cmd and ":" in (left := cmd.split(" | ", 1)[0]):
        jn, desc = left.split(":", 1)
        return ("build", {"job": jn.strip(), "desc": desc.strip(), "cmd": cmd.split(" | ", 1)[1].strip()})

    return ("unknown", None)

def process_command(cmd):
    """Execute command (may include user interactions)"""
    if not (cmd := cmd.strip()): return None

    action, data = parse_and_route_command(cmd)

    if action == "quit": return "Shutting down..."
    if action == "menu":
        # Signal TUI to exit temporarily for menu
        return "__SHOW_MENU__"
    if action == "run":
        with builder_lock:
            if data in task_builder:
                task_queue.put({"name": data, "steps": task_builder[data].copy()})
                del task_builder[data]
                return f"✓ Queued: {data}"
            return f"✗ Not found: {data}"
    if action == "attach": return open_terminal(data)
    if action == "attach_error": return data
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
    return "✗ Unknown command"

def worker():
    while running:
        try:
            execute_task(task_queue.get(timeout=0.5))
            task_queue.task_done()
        except Empty: continue
        except: continue

def watch_folder():
    """Watch for new task files - only auto-execute tasks without template variables"""
    tasks_dir = Path("tasks")
    tasks_dir.mkdir(exist_ok=True)
    while running:
        try:
            for json_file in tasks_dir.glob("*.json"):
                with processed_files_lock:
                    if json_file in processed_files: continue
                    processed_files.add(json_file)
                try:
                    task = json.loads(json_file.read_text())
                    # Skip tasks with template variables - they need user input via menu
                    if extract_variables(task):
                        continue
                    task_queue.put(task)
                except: pass
            sleep(1)
        except: pass

def run_tui_mode(selected_tasks):
    """NOTE: Not timed - includes user interaction time"""
    global running
    for t in selected_tasks:
        task_queue.put(t)
        print(f"✓ Queued: {t['name']}")

    [Thread(target=worker, daemon=True).start() for _ in range(4)]
    Thread(target=watch_folder, daemon=True).start()

    show_menu_flag = False

    while running:
        status_control = FormattedTextControl(text=get_status_text, focusable=False)
        status_window = Window(content=status_control, dont_extend_height=True)
        input_field = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)
        output_field = TextArea(height=3, focusable=False, scrollbar=False, read_only=True, text="")
        container = HSplit([status_window, output_field, input_field])

        kb = KeyBindings()
        @kb.add('enter')
        def _(event):
            nonlocal show_menu_flag
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
                    results.append(r)

            if results: output_field.text = '\n'.join(results) if len(results) > 1 else results[0]
            if not running: event.app.exit()

        @kb.add('c-c')
        def _(event):
            global running
            running = False
            event.app.exit()

        style = Style.from_dict({
            'header': '#ff00ff bold', 'label': '#00ffff bold', 'separator': '#888888',
            'text': '#ffffff', 'dim': '#666666', 'success': '#00ff00 bold',
            'error': '#ff0000 bold', 'running': '#ffff00 bold', 'help': '#888888', 'command': '#00ffff'
        })

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

# Simple mode (like git batch operations)
def run_simple_mode(selected_tasks):
    """NOTE: Not timed - waits for user commands to complete"""
    if not selected_tasks: return print("No tasks selected")

    print(f"\nStarting {len(selected_tasks)} task(s)...")
    threads = [Thread(target=execute_task, args=(t,)) for t in selected_tasks]
    [t.start() for t in threads]

    # Wait for completion - threads block internally (event-driven)
    [t.join() for t in threads]

    sep = "="*80
    with jobs_lock:
        print(f"\n{sep}")
        [print(f"{n}: {info['status']} | {info['step']}") for n, info in jobs.items()]
        print(sep)

    print("\n✓ All tasks complete!")

# Test mode (like git fsck) - integrated testing
def run_tests():
    """Run built-in tests for AIOS functionality"""
    print("="*80)
    print("AIOS Built-in Tests")
    print("="*80)
    print()

    failed = []

    # Test 0: AIOS overhead functions (UI responsiveness)
    print("0. Testing AIOS overhead functions...")
    try:
        # Test variable functions
        task = {"name": "test", "steps": [{"desc": "{{action}}", "cmd": "echo {{message}}"}]}
        vars = extract_variables(task)
        if "action" not in vars or "message" not in vars:
            raise Exception("Variable extraction failed")

        sub = substitute_variables(task, {"action": "run", "message": "world"})
        if "run" not in str(sub) or "world" not in str(sub):
            raise Exception("Variable substitution failed")

        # Test UI rendering
        status = get_status_text()
        if len(status) < 5:
            raise Exception("Status rendering failed")

        # Test command parsing
        for cmd in ["q", "m", "r test", "a job", "c job", "a 1"]:
            if not parse_and_route_command(cmd):
                raise Exception(f"Command parsing failed: {cmd}")

        print("   ✓ All overhead functions working")
        print(f"   ✓ Timings: extract={timings_current.get('extract_variables',0)*1000:.2f}ms, " +
              f"substitute={timings_current.get('substitute_variables',0)*1000:.2f}ms, " +
              f"parse={timings_current.get('parse_and_route_command',0)*1000:.2f}ms, " +
              f"render={timings_current.get('get_status_text',0)*1000:.2f}ms")

    except Exception as e:
        print(f"   ✗ Failed: {e}")
        failed.append("AIOS overhead")

    print()

    # Test 1: PTY terminal creation
    print("1. Testing PTY terminal creation...")
    try:
        # Create test session
        test_session = server.new_session("test-aios-pty", window_command="bash", attach=False)
        sleep(1)

        # Test PTY creation
        master = get_or_create_terminal("test-aios-pty")
        if master < 0:
            raise Exception("Invalid master fd")

        # Write and read
        os.write(master, b"echo TEST_PTY_OK\n")
        sleep(0.5)
        os.set_blocking(master, False)
        output = b""
        try:
            for _ in range(5):
                output += os.read(master, 4096)
        except BlockingIOError:
            pass

        if b"TEST_PTY_OK" in output:
            print("   ✓ PTY creation and I/O working")
        else:
            raise Exception("PTY output not received")

        # Cleanup
        test_session.kill()
        del _terminal_sessions["test-aios-pty"]

    except Exception as e:
        print(f"   ✗ Failed: {e}")
        failed.append("PTY terminal creation")

    # Test 2: WebSocket server
    print("\n2. Testing WebSocket server...")
    try:
        # Create test session
        test_session = server.new_session("test-aios-ws", window_command="bash", attach=False)
        sleep(1)

        # Start servers
        start_ws_server()
        sleep(2)

        if not ws_server_running:
            raise Exception("WebSocket server not running")

        print(f"   ✓ Servers started (HTTP:{ws_port}, WS:{ws_port + 1})")

        # Test WebSocket connection
        async def test_ws():
            try:
                uri = f"ws://localhost:{ws_port + 1}/attach/test-aios-ws"
                async with websockets.connect(uri) as ws:
                    await ws.send(b"echo WS_TEST\n")
                    for _ in range(10):
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            if b"WS_TEST" in msg:
                                return True
                        except asyncio.TimeoutError:
                            continue
            except Exception as e:
                raise Exception(f"WebSocket connection failed: {e}")
            return False

        if asyncio.run(test_ws()):
            print("   ✓ WebSocket connection and communication working")
        else:
            raise Exception("WebSocket test failed")

        # Cleanup
        test_session.kill()
        if "test-aios-ws" in _terminal_sessions:
            del _terminal_sessions["test-aios-ws"]

    except Exception as e:
        print(f"   ✗ Failed: {e}")
        failed.append("WebSocket server")

    # Test 3: HTTP server with query strings
    print("\n3. Testing HTTP server...")
    try:
        # Create terminal.html
        html_file = Path("terminal.html")
        html_file.write_text("<html><body>TEST_HTML</body></html>")

        # Test HTTP GET
        import urllib.request
        response = urllib.request.urlopen(f"http://localhost:{ws_port}/terminal.html?session=test", timeout=5)
        content = response.read().decode()

        if "TEST_HTML" in content:
            print("   ✓ HTTP server serving with query strings")
        else:
            raise Exception("HTTP server returned unexpected content")

        # Cleanup
        html_file.unlink()

    except Exception as e:
        print(f"   ✗ Failed: {e}")
        failed.append("HTTP server")

    # Summary
    print("\n" + "="*80)
    if not failed:
        print("✓ ALL TESTS PASSED")
        print("="*80)
        return 0
    else:
        print(f"✗ {len(failed)} TEST(S) FAILED")
        for test in failed:
            print(f"  - {test}")
        print("="*80)
        return 1

def main():
    """NOTE: Not timed - orchestrates entire program including I/O and user interaction"""
    # Test mode (like git fsck)
    if "--test" in sys.argv:
        sys.exit(run_tests())

    print("Loading AIOS...")

    # Mode detection inspired by git (--simple flag or default to TUI)
    simple_mode = "--simple" in sys.argv or "-s" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ["--simple", "-s", "--profile"]]

    # Load tasks from command line only (menu moved to TUI 'm' command)
    selected_tasks = []
    for fp in args:
        try:
            task = json.loads(Path(fp).read_text())
            # Prompt for variables if task has templates
            if task := prompt_for_variables(task):
                selected_tasks.append(task)
                print(f"✓ Loaded: {task['name']}")
        except Exception as e:
            print(f"✗ Error loading {fp}: {e}")

    # Run in appropriate mode
    if simple_mode:
        run_simple_mode(selected_tasks)
    else:
        run_tui_mode(selected_tasks)

    # Save profiling data
    if profile_mode and timings_current:
        save_timings(timings_current)
        print(f"\n✓ Saved {len(timings_current)} function timings to {TIMINGS_FILE}")

if __name__ == "__main__":
    main()
