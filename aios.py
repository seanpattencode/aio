#!/usr/bin/env python3
"""AIOS Task Manager - git-inspired design

Usage:
    aios.py [--simple|-s] [task.json ...]

Modes:
    Default: Interactive TUI with task builder
    --simple: Batch execution with simple monitoring

Examples:
    ./aios.py                    # Interactive menu + TUI
    ./aios.py task.json          # Load task, run in TUI
    ./aios.py --simple task.json # Batch mode
"""

import libtmux, json, sys, re, shutil
from datetime import datetime
from time import sleep
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

# Global state
server, jobs, jobs_lock = libtmux.Server(), {}, Lock()
task_queue, task_builder, builder_lock = Queue(), {}, Lock()
running, processed_files, processed_files_lock = True, set(), Lock()
JOBS_DIR, MAX_JOB_DIRS = Path("jobs"), 20

# Core functions (plumbing - inspired by git's core)
def extract_variables(obj):
    if isinstance(obj, str): return set(re.findall(r'\{\{(\w+)\}\}', obj))
    if isinstance(obj, dict): return set().union(*(extract_variables(v) for v in obj.values()))
    if isinstance(obj, list): return set().union(*(extract_variables(i) for i in obj))
    return set()

def substitute_variables(obj, values):
    if isinstance(obj, str):
        for var, val in values.items(): obj = obj.replace(f'{{{{{var}}}}}', str(val))
        return obj
    if isinstance(obj, dict): return {k: substitute_variables(v, values) for k, v in obj.items()}
    if isinstance(obj, list): return [substitute_variables(i, values) for i in obj]
    return obj

def prompt_for_variables(task):
    variables = extract_variables(task)
    if not variables: return task
    defaults = task.get('variables', {})

    print("\n" + "="*80 + "\nTEMPLATE PREVIEW\n" + "="*80)
    print(json.dumps(task, indent=2) + "\n" + "="*80)
    print("\n" + "="*80 + "\nDEFAULT VARIABLE VALUES\n" + "="*80)
    for var in sorted(variables):
        default = defaults.get(var, '(no default)')
        print(f"  {var}: {str(default)[:60] + '...' if len(str(default)) > 60 else default}")
    print("="*80 + "\n" + "="*80 + "\nTASK VARIABLES\n" + "="*80)

    values = {}
    for var in sorted(variables):
        default = defaults.get(var, '')
        prompt_text = f"{var} [{str(default)[:30] + '...' if len(str(default)) > 30 else default}]: " if default else f"{var}: "
        values[var] = (user_input := input(prompt_text).strip()) if user_input else default

    print("="*80)
    substituted = substitute_variables(task, values)
    print("\n" + "="*80 + "\nFINAL PREVIEW\n" + "="*80)
    print(json.dumps(substituted, indent=2) + "\n" + "="*80)

    if (conf := input("Launch this task? [Y/n]: ").strip().lower()) and conf not in ['y', 'yes']:
        print("Task cancelled")
        return None
    return substituted

def cleanup_old_jobs():
    if not JOBS_DIR.exists(): return
    for old in sorted(JOBS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[MAX_JOB_DIRS:]:
        try: shutil.rmtree(old)
        except: pass

def get_session(name): return next((s for s in server.sessions if s.name == name), None)
def kill_session(name):
    if sess := get_session(name): sess.kill()

def wait_ready(name, timeout=300):
    last_output, checks = "", 0
    while checks < timeout:
        sleep(2)
        if not (sess := get_session(name)): return False
        try:
            current = "\n".join(sess.windows[0].panes[0].capture_pane())
            if current == last_output and len(current) > 0: return True
            last_output = current
        except: return False
        checks += 2
    return False

def execute_task(task):
    name, steps = task["name"], task["steps"]
    repo, branch = task.get("repo"), task.get("branch", "main")
    ts, session_name = datetime.now().strftime("%Y%m%d_%H%M%S"), f"aios-{task['name']}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    JOBS_DIR.mkdir(exist_ok=True)
    job_dir, worktree_dir = JOBS_DIR / f"{name}-{ts}", (JOBS_DIR / f"{name}-{ts}" / "worktree") if repo else None

    try:
        with jobs_lock: jobs[name] = {"step": "Initializing...", "status": "⟳ Running"}
        kill_session(session_name)
        sleep(0.5)

        if not (session := server.new_session(session_name, window_command="bash --norc --noprofile", attach=False)):
            with jobs_lock: jobs[name] = {"step": "Failed to create session", "status": "✗ Error"}
            return

        sleep(1)
        pane = session.windows[0].panes[0]
        pane.send_keys(f"mkdir -p {job_dir}")
        sleep(1)

        if repo:
            worktree_abs = worktree_dir.absolute()
            with jobs_lock: jobs[name] = {"step": f"Creating worktree at {worktree_abs}", "status": "⟳ Running"}
            pane.send_keys(f"cd {repo} && git worktree add --detach {worktree_abs} {branch}")
            if not wait_ready(session_name, timeout=30):
                with jobs_lock: jobs[name] = {"step": "Failed to create worktree", "status": "✗ Error"}
                return
            pane.send_keys(f"cd {worktree_abs}")
            sleep(1)
        else:
            pane.send_keys(f"cd {job_dir}")
            sleep(1)

        work_dir = str(worktree_dir) if worktree_dir else str(job_dir)
        pane.send_keys(f"echo 'Working in: {work_dir}'")
        sleep(1)

        for i, step in enumerate(steps, 1):
            with jobs_lock: jobs[name] = {"step": f"{i}/{len(steps)}: {step['desc']} @ {work_dir}", "status": "⟳ Running"}
            pane.send_keys(step["cmd"])
            if not wait_ready(session_name, timeout=120):
                with jobs_lock: jobs[name] = {"step": f"Timeout on step {i}", "status": "✗ Timeout"}
                return

        with jobs_lock: jobs[name] = {"step": f"Completed @ {work_dir}", "status": "✓ Done"}
        cleanup_old_jobs()
    except Exception as e:
        with jobs_lock: jobs[name] = {"step": str(e)[:50], "status": "✗ Error"}

def show_task_menu():
    tasks_dir = Path("tasks")
    if not tasks_dir.exists(): return []
    if not (task_files := sorted(tasks_dir.glob("*.json"))): return []

    print("\n" + "="*80 + "\nAVAILABLE TASKS\n" + "="*80)
    tasks = []
    for i, filepath in enumerate(task_files, 1):
        try:
            with open(filepath) as f: task = json.load(f)
            tasks.append((filepath, task))
            has_wt, has_vars = '✓' if task.get('repo') else ' ', '⚙' if extract_variables(task) else ' '
            print(f"\n  {i}. [{has_wt}] [{has_vars}] {task.get('name', filepath.stem)}")

            for j, step in enumerate((steps := task.get('steps', []))[:5], 1):
                print(f"      {j}. {step.get('desc', 'No description')[:50]}")
            if len(steps) > 5: print(f"      ... and {len(steps) - 5} more steps")

            if variables := extract_variables(task):
                defaults = task.get('variables', {})
                print(f"      Variables: {', '.join(sorted(variables))}")
                if defaults: print(f"      Defaults: {len(defaults)} provided")
        except: pass

    with processed_files_lock:
        for filepath, _ in tasks: processed_files.add(filepath)

    print("\n" + "="*80 + "\nLegend: [✓]=Worktree [⚙]=Variables\n" + "="*80)
    print("Select tasks:\n  - Numbers (e.g., '1 3 5' or '1,3,5')\n  - 'all' for all tasks\n  - Enter to skip\n" + "="*80)

    if not (sel := input("Selection: ").strip()): return []

    selected = [task for _, task in tasks] if sel.lower() == 'all' else [
        tasks[int(p) - 1][1] for p in sel.replace(',', ' ').split()
        if p.isdigit() and 0 <= int(p) - 1 < len(tasks)
    ]

    return [pt for task in selected if (pt := prompt_for_variables(task)) is not None]

# TUI mode (porcelain - inspired by git's interactive commands)
def get_status_text():
    lines = [("class:header", "=" * 80 + "\nAIOS Task Manager - Live Status\n" + "=" * 80 + "\n"),
             ("class:label", "\nRunning Jobs:\n"), ("class:separator", "-" * 80 + "\n")]

    with jobs_lock:
        if jobs:
            for job_name, info in sorted(jobs.items()):
                status, step = info["status"], info["step"][:50]
                style = "class:success" if "✓" in status else "class:error" if "✗" in status else "class:running"
                lines.extend([("class:text", f"  {job_name:15} | {step:50} | "), (style, f"{status}\n")])
        else:
            lines.append(("class:dim", "  (no running jobs)\n"))

    lines.extend([("class:label", "\nTask Builder:\n"), ("class:separator", "-" * 80 + "\n")])
    with builder_lock:
        if task_builder:
            for job_name, steps in sorted(task_builder.items()):
                lines.append(("class:text", f"  {job_name}:\n"))
                for i, step in enumerate(steps, 1): lines.append(("class:text", f"    {i}. {step['desc'][:70]}\n"))
        else:
            lines.append(("class:dim", "  (no tasks being built)\n"))

    lines.extend([("class:separator", "\n" + "=" * 80 + "\n"), ("class:help", "Commands: "),
                  ("class:command", "<job>: <desc> | <cmd>"), ("class:help", "  |  "),
                  ("class:command", "run <job>"), ("class:help", "  |  "),
                  ("class:command", "clear <job>"), ("class:help", "  |  "),
                  ("class:command", "quit"), ("class:separator", "\n" + "=" * 80 + "\n\n")])
    return FormattedText(lines)

def process_command(cmd):
    global running
    if not (cmd := cmd.strip()): return None
    if cmd == "quit":
        running = False
        return "Shutting down..."
    if cmd.startswith("run "):
        job_name = cmd[4:].strip()
        with builder_lock:
            if job_name in task_builder:
                task_queue.put({"name": job_name, "steps": task_builder[job_name].copy()})
                del task_builder[job_name]
                return f"✓ Queued job: {job_name}"
            return f"✗ Job '{job_name}' not found in builder"
    if cmd.startswith("clear "):
        job_name = cmd[6:].strip()
        with builder_lock:
            if job_name in task_builder:
                del task_builder[job_name]
                return f"✓ Cleared job: {job_name}"
            return f"✗ Job '{job_name}' not found"
    if " | " in cmd and (parts := cmd.split(" | ", 1)) and len(parts) == 2:
        left, command = parts
        if ":" in left:
            job_name, desc = left.split(":", 1)
            job_name, desc, command = job_name.strip(), desc.strip(), command.strip()
            with builder_lock:
                if job_name not in task_builder: task_builder[job_name] = []
                task_builder[job_name].append({"desc": desc, "cmd": command})
            return f"✓ Added step to {job_name}"
        return "✗ Invalid format (missing ':' between job and description)"
    return "✗ Unknown command"

def worker():
    while running:
        try:
            execute_task(task_queue.get(timeout=0.5))
            task_queue.task_done()
        except Empty: continue
        except: continue

def watch_folder():
    tasks_dir = Path("tasks")
    tasks_dir.mkdir(exist_ok=True)
    while running:
        try:
            for json_file in tasks_dir.glob("*.json"):
                with processed_files_lock:
                    if json_file in processed_files: continue
                    processed_files.add(json_file)
                try:
                    with open(json_file) as f: task_queue.put(json.load(f))
                except: pass
            sleep(1)
        except: pass

def run_tui_mode(selected_tasks):
    global running
    for task in selected_tasks:
        task_queue.put(task)
        print(f"✓ Queued: {task['name']}")

    for w in [Thread(target=worker, daemon=True) for _ in range(4)]: w.start()
    Thread(target=watch_folder, daemon=True).start()

    status_control = FormattedTextControl(text=get_status_text, focusable=False)
    status_window = Window(content=status_control, dont_extend_height=True)
    input_field = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)
    output_field = TextArea(height=3, focusable=False, scrollbar=False, read_only=True, text="")
    container = HSplit([status_window, output_field, input_field])

    kb = KeyBindings()
    @kb.add('enter')
    def _(event):
        global running
        cmd, input_field.text = input_field.text, ""
        if result := process_command(cmd): output_field.text = result
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
    sleep(0.5)
    try: app.run()
    except KeyboardInterrupt: pass
    running = False
    print("\nShutdown complete.")

# Simple mode (like git batch operations)
def run_simple_mode(selected_tasks):
    if not selected_tasks:
        print("No tasks selected")
        return

    print(f"\nStarting {len(selected_tasks)} task(s)...")
    threads = [Thread(target=execute_task, args=(task,)) for task in selected_tasks]
    for t in threads:
        t.start()
        sleep(0.5)

    # Monitor
    for i in range(60):
        sleep(1)
        with jobs_lock:
            if not jobs: continue
            if i % 2 == 0:
                print(f"[{i}s] {' | '.join(f'{n}: {info['status']}' for n, info in jobs.items())}")
            if all("Done" in j['status'] or "Error" in j['status'] for j in jobs.values()):
                break

    print("\n" + "="*80)
    with jobs_lock:
        for name, info in jobs.items(): print(f"{name}: {info['status']} | {info['step']}")
    print("="*80)

    for t in threads: t.join()
    print("\n✓ All tasks complete!")

def main():
    print("Loading AIOS Task Manager...")

    # Mode detection inspired by git (--simple flag or default to TUI)
    simple_mode = "--simple" in sys.argv or "-s" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ["--simple", "-s"]]

    # Load tasks from menu or command line
    if not args:
        selected_tasks = show_task_menu()
    else:
        selected_tasks = []
        for filepath in args:
            try:
                with open(filepath) as f:
                    task = json.load(f)
                    selected_tasks.append(task)
                    print(f"✓ Loaded: {task['name']}")
            except Exception as e:
                print(f"✗ Error loading {filepath}: {e}")

    # Run in appropriate mode
    if simple_mode:
        run_simple_mode(selected_tasks)
    else:
        run_tui_mode(selected_tasks)

if __name__ == "__main__":
    main()
