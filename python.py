#!/usr/bin/env python3
"""AIOS Task Manager with prompt_toolkit"""

import libtmux
import json
import sys
from datetime import datetime
from time import sleep
from threading import Thread, Lock
from queue import Queue, Empty
from pathlib import Path
import shutil
import glob

from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.application import get_app
from prompt_toolkit.styles import Style

server = libtmux.Server()
jobs = {}
jobs_lock = Lock()
task_queue = Queue()
task_builder = {}
builder_lock = Lock()
running = True
processed_files = set()  # Track files already queued from menu
processed_files_lock = Lock()

JOBS_DIR = Path("jobs")
MAX_JOB_DIRS = 20  # Keep last 20 job directories

def cleanup_old_jobs():
    """Remove old job directories, keeping only the most recent MAX_JOB_DIRS"""
    if not JOBS_DIR.exists():
        return

    job_dirs = sorted(JOBS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)

    for old_dir in job_dirs[MAX_JOB_DIRS:]:
        try:
            shutil.rmtree(old_dir)
        except:
            pass

def get_session(name):
    return next((s for s in server.sessions if s.name == name), None)

def kill_session(name):
    sess = get_session(name)
    if sess:
        sess.kill()

def wait_ready(name, timeout=300):
    """Wait for command to complete by checking if output stabilizes"""
    last_output = ""
    checks = 0
    while checks < timeout:
        sleep(2)
        sess = get_session(name)
        if not sess:
            return False
        try:
            current = "\n".join(sess.windows[0].panes[0].capture_pane())
            if current == last_output and len(current) > 0:
                return True
            last_output = current
        except:
            return False
        checks += 2
    return False

def get_status_text():
    """Generate the status display text"""
    lines = []

    lines.append(("class:header", "=" * 80))
    lines.append(("class:header", "\nAIOS Task Manager - Live Status\n"))
    lines.append(("class:header", "=" * 80 + "\n"))

    # Running Jobs
    lines.append(("class:label", "\nRunning Jobs:\n"))
    lines.append(("class:separator", "-" * 80 + "\n"))

    with jobs_lock:
        if jobs:
            for job_name, info in sorted(jobs.items()):
                status = info["status"]
                step = info["step"][:50]

                if "✓" in status:
                    status_style = "class:success"
                elif "✗" in status:
                    status_style = "class:error"
                else:
                    status_style = "class:running"

                lines.append(("class:text", f"  {job_name:15} | {step:50} | "))
                lines.append((status_style, f"{status}\n"))
        else:
            lines.append(("class:dim", "  (no running jobs)\n"))

    # Task Builder
    lines.append(("class:label", "\nTask Builder:\n"))
    lines.append(("class:separator", "-" * 80 + "\n"))

    with builder_lock:
        if task_builder:
            for job_name, steps in sorted(task_builder.items()):
                lines.append(("class:text", f"  {job_name}:\n"))
                for i, step in enumerate(steps, 1):
                    desc = step['desc'][:70]
                    lines.append(("class:text", f"    {i}. {desc}\n"))
        else:
            lines.append(("class:dim", "  (no tasks being built)\n"))

    # Footer
    lines.append(("class:separator", "\n" + "=" * 80 + "\n"))
    lines.append(("class:help", "Commands: "))
    lines.append(("class:command", "<job>: <desc> | <cmd>"))
    lines.append(("class:help", "  |  "))
    lines.append(("class:command", "run <job>"))
    lines.append(("class:help", "  |  "))
    lines.append(("class:command", "clear <job>"))
    lines.append(("class:help", "  |  "))
    lines.append(("class:command", "quit"))
    lines.append(("class:separator", "\n" + "=" * 80 + "\n\n"))

    return FormattedText(lines)

def execute_task(task):
    """Execute a task with its steps in separate tmux session"""
    name = task["name"]
    steps = task["steps"]
    repo = task.get("repo")
    branch = task.get("branch", "main")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"aios-{name}-{ts}"

    # Create jobs directory
    JOBS_DIR.mkdir(exist_ok=True)
    job_dir = JOBS_DIR / f"{name}-{ts}"
    worktree_dir = job_dir / "worktree" if repo else None

    try:
        with jobs_lock:
            jobs[name] = {"step": "Initializing...", "status": "⟳ Running"}

        kill_session(session_name)
        sleep(0.5)

        session = server.new_session(session_name, window_command="bash --norc --noprofile", attach=False)
        sleep(1)

        if not session:
            with jobs_lock:
                jobs[name] = {"step": "Failed to create session", "status": "✗ Error"}
            return

        pane = session.windows[0].panes[0]

        # Create job directory
        pane.send_keys(f"mkdir -p {job_dir}")
        sleep(1)

        # Create worktree if repo specified
        if repo:
            worktree_dir_abs = worktree_dir.absolute()
            with jobs_lock:
                jobs[name] = {"step": f"Creating worktree at {worktree_dir_abs}", "status": "⟳ Running"}
            # Use --detach to avoid branch conflicts
            pane.send_keys(f"cd {repo} && git worktree add --detach {worktree_dir_abs} {branch}")
            if not wait_ready(session_name, timeout=30):
                with jobs_lock:
                    jobs[name] = {"step": "Failed to create worktree", "status": "✗ Error"}
                return
            pane.send_keys(f"cd {worktree_dir_abs}")
            sleep(1)
        else:
            pane.send_keys(f"cd {job_dir}")
            sleep(1)

        # Log working directory
        work_dir = str(worktree_dir) if worktree_dir else str(job_dir)
        pane.send_keys(f"echo 'Working in: {work_dir}'")
        sleep(1)

        for i, step in enumerate(steps, 1):
            with jobs_lock:
                jobs[name] = {"step": f"{i}/{len(steps)}: {step['desc']} @ {work_dir}", "status": "⟳ Running"}

            pane.send_keys(step["cmd"])

            if not wait_ready(session_name, timeout=120):
                with jobs_lock:
                    jobs[name] = {"step": f"Timeout on step {i}", "status": "✗ Timeout"}
                return

        # Cleanup worktree if created - DISABLED (keeping worktrees for inspection)
        # if repo and worktree_dir:
        #     worktree_dir_abs = worktree_dir.absolute()
        #     with jobs_lock:
        #         jobs[name] = {"step": f"Cleaning up worktree", "status": "⟳ Running"}
        #     pane.send_keys(f"cd {repo} && git worktree remove {worktree_dir_abs} --force")
        #     sleep(2)

        with jobs_lock:
            jobs[name] = {"step": f"Completed @ {work_dir}", "status": "✓ Done"}

        # Cleanup old job directories
        cleanup_old_jobs()

    except Exception as e:
        with jobs_lock:
            jobs[name] = {"step": str(e)[:50], "status": "✗ Error"}

def worker():
    """Worker thread to process tasks from queue"""
    while running:
        try:
            task = task_queue.get(timeout=0.5)
            execute_task(task)
            task_queue.task_done()
        except Empty:
            continue
        except Exception:
            continue

def watch_folder():
    """Watch tasks/ folder for new .json files"""
    tasks_dir = Path("tasks")
    tasks_dir.mkdir(exist_ok=True)

    while running:
        try:
            for json_file in tasks_dir.glob("*.json"):
                with processed_files_lock:
                    if json_file in processed_files:
                        continue
                    processed_files.add(json_file)

                try:
                    with open(json_file) as f:
                        task = json.load(f)
                    task_queue.put(task)
                except:
                    pass

            sleep(1)
        except:
            pass

def process_command(cmd):
    """Process a user command"""
    global running

    cmd = cmd.strip()
    if not cmd:
        return None

    if cmd == "quit":
        running = False
        return "Shutting down..."

    elif cmd.startswith("run "):
        job_name = cmd[4:].strip()
        with builder_lock:
            if job_name in task_builder:
                task = {
                    "name": job_name,
                    "steps": task_builder[job_name].copy()
                }
                task_queue.put(task)
                del task_builder[job_name]
                return f"✓ Queued job: {job_name}"
            else:
                return f"✗ Job '{job_name}' not found in builder"

    elif cmd.startswith("clear "):
        job_name = cmd[6:].strip()
        with builder_lock:
            if job_name in task_builder:
                del task_builder[job_name]
                return f"✓ Cleared job: {job_name}"
            else:
                return f"✗ Job '{job_name}' not found"

    elif " | " in cmd:
        parts = cmd.split(" | ", 1)
        if len(parts) == 2:
            left, command = parts
            if ":" in left:
                job_name, desc = left.split(":", 1)
                job_name = job_name.strip()
                desc = desc.strip()
                command = command.strip()

                with builder_lock:
                    if job_name not in task_builder:
                        task_builder[job_name] = []
                    task_builder[job_name].append({
                        "desc": desc,
                        "cmd": command
                    })
                return f"✓ Added step to {job_name}"
            else:
                return "✗ Invalid format (missing ':' between job and description)"
        else:
            return "✗ Invalid format (missing ' | ')"
    else:
        return "✗ Unknown command"

def show_task_menu():
    """Scan tasks/ folder and show interactive menu"""
    tasks_dir = Path("tasks")
    if not tasks_dir.exists():
        return []

    task_files = sorted(tasks_dir.glob("*.json"))
    if not task_files:
        return []

    print("\n" + "="*80)
    print("AVAILABLE TASKS")
    print("="*80)

    tasks = []
    for i, filepath in enumerate(task_files, 1):
        try:
            with open(filepath) as f:
                task = json.load(f)
                tasks.append((filepath, task))
                task_name = task.get('name', filepath.stem)
                has_worktree = '✓' if task.get('repo') else ' '
                print(f"  {i}. [{has_worktree}] {task_name:30} ({filepath.name})")
        except:
            pass

    # Mark ALL task files as processed so watch_folder won't auto-queue them
    with processed_files_lock:
        for filepath, _ in tasks:
            processed_files.add(filepath)

    print("="*80)
    print("Select tasks to run:")
    print("  - Enter numbers (e.g., '1 3 5' or '1,3,5')")
    print("  - Enter 'all' to run all tasks")
    print("  - Press Enter to skip and use interactive mode")
    print("="*80)

    selection = input("Selection: ").strip()

    if not selection:
        return []

    if selection.lower() == 'all':
        return [task for _, task in tasks]

    # Parse selection
    selected = []
    parts = selection.replace(',', ' ').split()
    for part in parts:
        try:
            idx = int(part) - 1
            if 0 <= idx < len(tasks):
                selected.append(tasks[idx][1])
        except:
            pass

    return selected

def main():
    global running

    print("Loading AIOS Task Manager...")

    # Show task menu if no command line args
    if len(sys.argv) == 1:
        selected_tasks = show_task_menu()
        for task in selected_tasks:
            task_queue.put(task)
            print(f"✓ Queued: {task['name']}")

    # Load tasks from command line args
    if len(sys.argv) > 1:
        for filepath in sys.argv[1:]:
            try:
                with open(filepath) as f:
                    task = json.load(f)
                    task_queue.put(task)
                    print(f"✓ Queued: {task['name']}")
            except Exception as e:
                print(f"✗ Error loading {filepath}: {e}")

    # Start worker threads
    workers = [Thread(target=worker, daemon=True) for _ in range(4)]
    for w in workers:
        w.start()

    # Start folder watcher
    watcher = Thread(target=watch_folder, daemon=True)
    watcher.start()

    # Create prompt_toolkit UI
    status_control = FormattedTextControl(
        text=get_status_text,
        focusable=False
    )

    status_window = Window(
        content=status_control,
        dont_extend_height=True
    )

    input_field = TextArea(
        height=1,
        prompt="❯ ",
        multiline=False,
        wrap_lines=False
    )

    output_field = TextArea(
        height=3,
        focusable=False,
        scrollbar=False,
        read_only=True,
        text=""
    )

    container = HSplit([
        status_window,
        output_field,
        input_field
    ])

    kb = KeyBindings()

    @kb.add('enter')
    def _(event):
        global running
        cmd = input_field.text
        input_field.text = ""

        result = process_command(cmd)
        if result:
            output_field.text = result

        if not running:
            event.app.exit()

    @kb.add('c-c')
    def _(event):
        global running
        running = False
        event.app.exit()

    # Style
    style = Style.from_dict({
        'header': '#ff00ff bold',
        'label': '#00ffff bold',
        'separator': '#888888',
        'text': '#ffffff',
        'dim': '#666666',
        'success': '#00ff00 bold',
        'error': '#ff0000 bold',
        'running': '#ffff00 bold',
        'help': '#888888',
        'command': '#00ffff',
    })

    app = Application(
        layout=Layout(container),
        key_bindings=kb,
        full_screen=True,
        style=style,
        mouse_support=False
    )

    # Update status in background
    def update_status():
        while running:
            sleep(0.5)
            try:
                app.invalidate()
            except:
                break

    updater = Thread(target=update_status, daemon=True)
    updater.start()

    sleep(0.5)  # Let workers start

    try:
        app.run()
    except KeyboardInterrupt:
        pass

    running = False
    print("\nShutdown complete.")

if __name__ == "__main__":
    main()
