#!/usr/bin/env python3
"""Claude Auto - Simplified automation tool for Claude CLI"""

import os, sys, json, time, subprocess, tempfile, shutil, threading, queue, select
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

__version__ = "6.1.0"

WORKFLOWS = {
    'standard': [
        ('Build', 'Before you begin read the files in this directory for context. Write all logic and functionality into a single .py file unless explicitly stated otherwise, no functionality is reliant on anything but this and it should run alone without any supporting files except if needed environmental setup.Set an aggressive target for low line count and stick to it if not given one.'),
        ('Debug', 'Run the existing code, debug it, and make it work well. Any changes should be extremely minimal just to fix problems and if it works don\'t change it.'),
        ('Finalize', 'Run it, debug it, and make it work well. Any changes should be extremely minimal just to fix problems and if it works don\'t change it. Then update/create the readme and simplify it aggressively. Everything must go except that which would make the user unable to use the script.')
    ],
    'simplify': [
        ('Build', 'Before you begin read the files in this directory for context. Write all logic and functionality into a single .py file unless explicitly stated otherwise, no functionality is reliant on anything but this and it should run alone without any supporting files except if needed environmental setup.Set an aggressive target for low line count and stick to it if not given one.'),
        ('Debug', 'Run the existing code, debug it, and make it work well. Any changes should be extremely minimal just to fix problems and if it works don\'t change it.'),
        ('Simplify', 'We are going to do a significant simplification. We will be deleting more than half of the lines of the single logical file without harming functionality, simplicity, following conventions, maintaining readability.'),
        ('Finalize', 'Run it, debug it, and make it work well. Any changes should be extremely minimal just to fix problems and if it works don\'t change it. Then update/create the readme and simplify it aggressively. Everything must go except that which would make the user unable to use the script.')
    ]
}

class ClaudeAuto:
    def __init__(self, output_dir="./claude_output", working_dir=None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        if not self.working_dir.exists():
            print(f"Working directory doesn't exist: {self.working_dir}")
            if input("Create it? (y/n): ").strip().lower() == 'y':
                self.working_dir.mkdir(parents=True, exist_ok=True)
            else:
                self.working_dir = Path.cwd()
        self.results = []
        self.active_tasks = {}
        self.task_lock = threading.Lock()
        self.completed_queue = queue.Queue()
        self.notification_thread = None
    

    def start_monitoring(self):
        """Start background monitoring"""
        # Clear screen
        print('\033[2J\033[H')

    def execute_claude(self, prompt, cwd=None, output_file=None, prefix="", task_id=None):
        """Execute Claude CLI with prompt"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            tmp.write(prompt)
            temp_file = tmp.name
        
        try:
            task_name = prefix.strip('[]').strip() if prefix else 'Task'
            if task_id:
                with self.task_lock:
                    self.active_tasks[task_id] = {'name': task_name, 'start': time.time()}

            cmd = f"claude --dangerously-skip-permissions < {temp_file} 2>&1 | head -c 500000"
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     cwd=str(cwd or self.working_dir), errors='replace')

            output_lines = []
            for line in process.stdout:
                # Don't print to console for background tasks
                output_lines.append(line)
                if output_file:
                    with open(output_file, 'a') as f:
                        f.write(line)
                        f.flush()
            
            exit_code = process.wait(timeout=300)
            os.unlink(temp_file)

            if task_id:
                with self.task_lock:
                    if task_id in self.active_tasks:
                        del self.active_tasks[task_id]

            return exit_code == 0, ''.join(output_lines)
        except Exception as e:
            print(f"Error: {e}")
            if task_id:
                with self.task_lock:
                    if task_id in self.active_tasks:
                        del self.active_tasks[task_id]
            return False, str(e)
    
    def run_task(self, name, prompt, task_id=None, future=None):
        """Run a single task"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_dir = self.output_dir / f"{name}_{timestamp}"
        task_dir.mkdir(exist_ok=True)
        output_file = task_dir / "output.txt"

        prefix = f"[{task_id}] " if task_id else ""

        with open(output_file, 'w') as f:
            f.write(f"=== {name} ===\n{datetime.now()}\n\n--- Prompt ---\n{prompt}\n{'='*60}\n\n")

        success, _ = self.execute_claude(prompt, cwd=task_dir, output_file=output_file, prefix=prefix, task_id=task_id)

        # Remove from active tasks and add to completed queue
        if task_id:
            with self.task_lock:
                if task_id in self.active_tasks:
                    del self.active_tasks[task_id]
            self.completed_queue.put((task_id, name, time.time()))

        result = {'name': name, 'success': success, 'output': str(output_file)}
        self.results.append(result)
        return result
    
    def run_workflow(self, workflow_type, initial_task, version_num=None, num_versions=1):
        """Run a complete workflow"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version_suffix = f"_v{version_num}" if version_num else ""
        # Use working_dir instead of output_dir when a custom directory is specified
        base_dir = self.working_dir if self.working_dir != Path.cwd() else self.output_dir
        workflow_dir = base_dir / f"workflow_{timestamp}{version_suffix}"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy files from working directory to workflow directory if needed
        if self.working_dir != Path.cwd() and self.working_dir.exists():
            print(f"\nCopying files from {self.working_dir}...")
            for item in self.working_dir.iterdir():
                if item.name.startswith('.') or item.name in ['__pycache__', 'node_modules', '.git', 'claude_output']:
                    continue
                dest = workflow_dir / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                elif item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
        
        # Always work in the workflow directory so files are saved there
        working_dir = workflow_dir
        
        output_file = workflow_dir / "output.txt"
        with open(output_file, 'w') as f:
            f.write(f"{'='*80}\nWORKFLOW EXECUTION - {datetime.now()}\n")
            if version_num:
                f.write(f"Version: {version_num}/{num_versions}\n")
            f.write(f"Initial Task: {initial_task[:100]}{'...' if len(initial_task) > 100 else ''}\n{'='*80}\n\n")
        
        results = []
        steps = WORKFLOWS[workflow_type]
        
        for i, (step_name, step_prompt) in enumerate(steps, 1):
            full_prompt = f"Working in: {working_dir}\n\n{initial_task if step_name == 'Build' else step_prompt}"
            
            with open(output_file, 'a') as f:
                f.write(f"\n{'#'*80}\nSTEP {i}/{len(steps)}: {step_name.upper()}\n{'#'*80}\n")
                f.write(f"\n--- Prompt for {step_name} ---\n{full_prompt}\n\n--- Claude Response ---\n")
            
            prefix = f"[V{version_num}] " if version_num else ""
            task_id = f"BGV{version_num}S{i}" if version_num else f"BGS{i}"
            # Don't print step messages for background workflows
            success, _ = self.execute_claude(full_prompt, cwd=working_dir, output_file=output_file, prefix=prefix, task_id=task_id)
            
            # Don't print step completion for background workflows
            results.append({'name': step_name, 'success': success})
            
            if not success:
                print(f"{prefix}Step failed, stopping workflow")
                break
        
        return {'version': version_num or 'single', 'directory': str(workflow_dir),
                'output': str(output_file), 'success': all(r['success'] for r in results)}

def get_dir_size(path):
    """Get directory size in MB"""
    total = sum(os.path.getsize(os.path.join(dp, f)) 
                for dp, _, fns in os.walk(path) 
                for f in fns if os.path.exists(os.path.join(dp, f)))
    return total / (1024 * 1024)

def main():
    """Main interactive loop"""
    import argparse
    parser = argparse.ArgumentParser(description='Claude Auto - Automation tool')
    parser.add_argument('-d', '--dir', dest='working_dir', help='Working directory')
    parser.add_argument('-o', '--output', default='./claude_output', help='Output directory')
    args = parser.parse_args()

    auto = ClaudeAuto(output_dir=args.output, working_dir=args.working_dir)
    auto.start_monitoring()
    
    # Check Claude CLI
    if subprocess.run(['which', 'claude'], capture_output=True).returncode != 0:
        print("Claude CLI not found! Install with: npm install -g @anthropic/claude-cli")
        sys.exit(1)
    
    print(f"\n{'='*60}\nClaude Auto v{__version__}\nWorking: {auto.working_dir}\nOutput: {auto.output_dir}\n{'='*60}")

    executor = ThreadPoolExecutor(max_workers=10)
    background_futures = []

    # Store recent notifications
    recent_notifications = []
    notification_lock = threading.Lock()

    def status_updater():
        """Background thread to update status and collect notifications"""
        while True:
            try:
                time.sleep(1)
                # Check for new completions
                while not auto.completed_queue.empty():
                    try:
                        task_id, name, completion_time = auto.completed_queue.get_nowait()
                        with notification_lock:
                            recent_notifications.append({
                                'msg': f"{name} completed [{task_id}]",
                                'time': time.time()
                            })
                            # Keep only last 10 notifications
                            if len(recent_notifications) > 10:
                                recent_notifications.pop(0)
                        # Print notification immediately
                        print(f"\n\033[93m{name} completed [{task_id}]\033[0m")
                        print("Choice: ", end='', flush=True)  # Re-show prompt
                    except:
                        break
            except:
                break

    # Start status updater thread
    status_thread = threading.Thread(target=status_updater, daemon=True)
    status_thread.start()

    def print_status():
        """Print current status with notifications"""
        # Clean old notifications (older than 30 seconds)
        with notification_lock:
            current_time = time.time()
            for notif in recent_notifications[:]:
                if current_time - notif['time'] > 30:
                    recent_notifications.remove(notif)

            # Show recent notifications
            if recent_notifications:
                for notif in recent_notifications[-3:]:  # Show last 3 notifications
                    print(f"\033[93m{notif['msg']}\033[0m")

        # Display status
        active_count = len(auto.active_tasks)
        if active_count > 0:
            active_list = ", ".join([f"{tid}" for tid in list(auto.active_tasks.keys())[:5]])
            print(f"\n\033[92mActive: {active_count} tasks [{active_list}]\033[0m")

    while True:
        # Clean up completed background tasks
        background_futures = [f for f in background_futures if not f.done()]

        print_status()

        print("\nOptions:\n1. Quick prompt\n2. Multiple tasks (parallel)\n3. Multiple tasks (sequential)")
        print(f"4. Workflow\n5. Exit")

        try:
            choice = input("\nChoice: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        if choice == '1':
            print("Enter prompt (Ctrl+D to finish):")
            try:
                lines = []
                while True:
                    lines.append(input())
            except EOFError:
                prompt = '\n'.join(lines).strip()
                if prompt:
                    task_id = f"BG{len(background_futures)+1}"
                    # Pre-register the task
                    with auto.task_lock:
                        auto.active_tasks[task_id] = {'name': 'Task', 'start': time.time()}
                    future = executor.submit(auto.run_task, 'Task', prompt, task_id, None)
                    with auto.task_lock:
                        if task_id in auto.active_tasks:
                            auto.active_tasks[task_id]['future'] = future
                    background_futures.append(future)
                    print(f"\nTask launched in background as {task_id}")
        
        elif choice in ['2', '3']:
            tasks = []
            print("\nEnter tasks (empty name to finish):")
            while True:
                name = input(f"Task {len(tasks)+1} name: ").strip()
                if not name:
                    break
                print("Prompt (Ctrl+D to finish):")
                try:
                    lines = []
                    while True:
                        lines.append(input())
                except EOFError:
                    prompt = '\n'.join(lines).strip()
                    if prompt:
                        tasks.append({'name': name, 'prompt': prompt})
            
            if tasks:
                base_id = len(background_futures)
                if choice == '2' and len(tasks) > 1:
                    # Parallel execution
                    futures = []
                    for i, t in enumerate(tasks):
                        task_id = f"BG{base_id+i+1}"
                        with auto.task_lock:
                            auto.active_tasks[task_id] = {'name': t['name'], 'start': time.time()}
                        future = executor.submit(auto.run_task, t['name'], t['prompt'], task_id, None)
                        with auto.task_lock:
                            if task_id in auto.active_tasks:
                                auto.active_tasks[task_id]['future'] = future
                        futures.append(future)
                    background_futures.extend(futures)
                    print(f"\n{len(tasks)} tasks launched in parallel")
                else:
                    # Sequential execution in background
                    def run_sequential():
                        for i, task in enumerate(tasks):
                            task_id = f"BG{base_id+i+1}"
                            with auto.task_lock:
                                auto.active_tasks[task_id] = {'name': task['name'], 'start': time.time()}
                            auto.run_task(task['name'], task['prompt'], task_id)
                    future = executor.submit(run_sequential)
                    background_futures.append(future)
                    print(f"\n{len(tasks)} tasks launched sequentially in background")
        
        elif choice == '4':
            print("\nWORKFLOW MODE")
            print(f"Working: {auto.working_dir}")
            
            # Workflow type
            print("\n1. Standard (3 steps)\n2. With simplification (4 steps)")
            wf_type = 'simplify' if input("Choice [1-2]: ").strip() == '2' else 'standard'
            
            # Number of versions
            num_versions = 1
            exec_mode = 'single'
            print("\n1. Single version\n2. Multiple versions")
            if input("Choice [1-2]: ").strip() == '2':
                try:
                    num_versions = max(1, min(10, int(input("Number of versions (2-10): ").strip())))
                    if num_versions > 1:
                        print("\n1. Parallel\n2. Sequential")
                        exec_mode = 'parallel' if input("Choice [1-2]: ").strip() == '1' else 'sequential'
                except:
                    num_versions = 2
            
            # Working directory
            if input("\nChange working directory? (y/n): ").strip().lower() == 'y':
                new_dir = input("Path: ").strip()
                if new_dir:
                    auto.working_dir = Path(new_dir)
                    if not auto.working_dir.exists():
                        auto.working_dir.mkdir(parents=True, exist_ok=True)
            
            # Check size for parallel copy
            if num_versions > 1 and exec_mode == 'parallel' and auto.working_dir != Path.cwd():
                size_mb = get_dir_size(auto.working_dir)
                if size_mb > 100:
                    print(f"\nWill copy {size_mb:.1f}MB. Continue in 10s (Ctrl+C to abort)...")
                    try:
                        for i in range(10, 0, -1):
                            print(f"\r{i}... ", end='', flush=True)
                            time.sleep(1)
                    except KeyboardInterrupt:
                        continue
            
            # Get task
            print("\nEnter task (Ctrl+D to finish):")
            try:
                lines = []
                while True:
                    lines.append(input())
            except EOFError:
                initial_task = '\n'.join(lines).strip()
            
            if not initial_task:
                continue
            
            print(f"\nStarting {num_versions} workflow(s)...")
            
            # Execute workflows in background
            if num_versions == 1:
                future = executor.submit(auto.run_workflow, wf_type, initial_task)
                background_futures.append(future)
                print(f"Workflow launched in background")
            elif exec_mode == 'parallel':
                futures = [executor.submit(auto.run_workflow, wf_type, initial_task, i+1, num_versions)
                         for i in range(num_versions)]
                background_futures.extend(futures)
                print(f"{num_versions} workflows launched in parallel")
            else:
                def run_sequential_workflows():
                    for i in range(num_versions):
                        auto.run_workflow(wf_type, initial_task, i+1, num_versions)
                future = executor.submit(run_sequential_workflows)
                background_futures.append(future)
                print(f"{num_versions} workflows launched sequentially")
        
        if choice == '5':
            break
        
        # Show results summary
        if auto.results:
            print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
            print(f"Successful: {sum(1 for r in auto.results if r.get('success'))}")
            print(f"Failed: {sum(1 for r in auto.results if not r.get('success'))}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\033[?25h")  # Show cursor
        print("\n\nInterrupted")
        sys.exit(130)