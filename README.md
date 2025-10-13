# AIOS Task Manager

A professional terminal UI for running multi-step jobs in parallel with live status updates. Perfect for managing codex workflows, build pipelines, or any multi-step automation.

## Features

✅ **Stable Input** - Type freely while status updates above (never disappears!)
✅ **Live Status** - Real-time job progress updates every 0.5 seconds
✅ **Interactive Builder** - Build multi-step jobs on the fly
✅ **Parallel Execution** - Run up to 4 jobs simultaneously
✅ **Git Worktree Support** - Run jobs in isolated git worktrees (parallel codex workflows!)
✅ **Isolated Sessions** - Each job runs in its own tmux session
✅ **Auto Cleanup** - Keeps last 20 job directories, removes older ones
✅ **Organized Output** - All job output in `jobs/` directory

## Installation

```bash
pip install prompt_toolkit libtmux
```

## Quick Start

### Start the Manager

```bash
./aios.py
```

**Task Menu** appears first, showing all tasks in `tasks/` folder:

```
================================================================================
AVAILABLE TASKS
================================================================================
  1. [✓] basic-worktree                 (basic-worktree.json)
  2. [✓] codex-worktree                 (codex-worktree.json)
  3. [ ] factor-demo                    (example_task.json)
  4. [ ] sorting-algo                   (parallel_task.json)
  5. [ ] simple-test                    (test_task.json)
================================================================================
Select tasks to run:
  - Enter numbers (e.g., '1 3 5' or '1,3,5')
  - Enter 'all' to run all tasks
  - Press Enter to skip and use interactive mode
================================================================================
Selection:
```

**[✓]** = Has git worktree support
**[ ]** = Regular task

After selection (or pressing Enter), you'll see the full-screen terminal UI:

```
================================================================================
AIOS Task Manager - Live Status
================================================================================

Running Jobs:
--------------------------------------------------------------------------------
  (no running jobs)

Task Builder:
--------------------------------------------------------------------------------
  (no tasks being built)

================================================================================
Commands: <job>: <desc> | <cmd>  |  run <job>  |  clear <job>  |  quit
================================================================================

❯ _
```

### Build and Run a Job

**Add steps to a job:**
```
❯ demo: Create file | echo 'Hello World' > test.txt
❯ demo: Show content | cat test.txt
❯ demo: List files | ls -la
```

The Task Builder section updates to show your job being constructed.

**Run the job:**
```
❯ run demo
```

Watch it progress through steps in real-time! The status changes from:
- ⟳ Running (yellow) → ✓ Done (green)

**Exit when done:**
```
❯ quit
```

Or press `Ctrl+C`

## Command Reference

### Build Jobs

```
<job-name>: <description> | <command>
```

Examples:
```
build: Compile code | make
build: Run tests | make test
build: Deploy | make deploy
```

### Execute Jobs

```
run <job-name>
```

Example:
```
❯ run build
```

### Clear Jobs

```
clear <job-name>
```

Removes a job from the builder without running it.

### Quit

```
quit
```

Or press `Ctrl+C`

## Real-World Examples

### Example 1: Codex Workflow

```
❯ factor: Create program | codex exec --model gpt-5-codex -- "create factor.py that factors numbers"
❯ factor: Test with 84 | python factor.py 84
❯ factor: Test with 100 | python factor.py 100
❯ run factor
```

### Example 2: Build Pipeline

```
❯ deploy: Run tests | pytest tests/
❯ deploy: Build Docker | docker build -t myapp:latest .
❯ deploy: Push image | docker push myapp:latest
❯ deploy: Update k8s | kubectl apply -f k8s/
❯ run deploy
```

### Example 3: Parallel Jobs

```
❯ job1: Task A | sleep 5 && echo 'Job 1 done'
❯ job2: Task B | sleep 3 && echo 'Job 2 done'
❯ job3: Task C | sleep 4 && echo 'Job 3 done'
❯ run job1
❯ run job2
❯ run job3
```

All three run simultaneously!

## Load from JSON Files

Create a task file `deploy.json`:

```json
{
  "name": "deploy-staging",
  "steps": [
    {"desc": "Run tests", "cmd": "pytest tests/"},
    {"desc": "Build Docker image", "cmd": "docker build -t api:latest ."},
    {"desc": "Push to registry", "cmd": "docker push api:latest"},
    {"desc": "Deploy to k8s", "cmd": "kubectl apply -f k8s/staging/"}
  ]
}
```

Load and run:

```bash
./aios.py deploy.json
```

Or load multiple tasks:

```bash
./aios.py deploy-staging.json deploy-prod.json deploy-eu.json
```

All will queue and run in parallel!

## Tasks Folder

Place your task JSON files in the `tasks/` directory. AIOS automatically scans this folder at startup and displays them in an interactive menu with steps preview.

### Task Organization

```
tasks/
├── basic-worktree.json     # ✓ With worktree
├── codex-worktree.json     # ✓ With worktree
├── template-codex.json     # ✓⚙ Worktree + Variables
├── template-parallel.json  # ✓⚙ Worktree + Variables
├── example_task.json       # Regular task
├── parallel_task.json      # Regular task
└── test_task.json          # Regular task
```

### Enhanced Menu Display

The menu now shows:
- **Task indicators**: `[✓]` = Worktree, `[⚙]` = Variables
- **Steps preview**: First 5 steps of each task
- **Variable list**: All {{variables}} in the task
- **Default values**: Number of defaults provided

Example:
```
  5. [✓] [⚙] template-codex
      1. Show directory
      2. Generate code via codex
      3. List created files
      4. Show first Python file
      Variables: branch_name, repo_path, task_description
      Defaults: 3 provided
```

### Interactive Menu

When you run `./aios.py` without arguments, you'll see a numbered menu of all tasks:

```bash
# Run specific tasks
./aios.py
# Select "1 3" to run tasks 1 and 3

# Run all tasks
./aios.py
# Select "all"

# Skip menu and use interactive mode
./aios.py
# Press Enter
```

### Using run.py (Simple Runner)

For a simpler, non-UI experience:

```bash
echo "1 2" | python run.py   # Run tasks 1 and 2
echo "all" | python run.py   # Run all tasks
```

## Template Variables

Create reusable task templates with dynamic `{{variable}}` placeholders. AIOS prompts you for values at runtime, with optional defaults.

### Variable Syntax

Use `{{variable_name}}` anywhere in your task JSON:

```json
{
  "name": "template-example",
  "repo": "{{repo_path}}",
  "branch": "{{branch_name}}",
  "variables": {
    "repo_path": "/default/path",
    "branch_name": "main",
    "task_description": "create a hello world function"
  },
  "steps": [
    {"desc": "Generate code", "cmd": "codex exec -- \"{{task_description}}\""},
    {"desc": "Test with {{test_size}}", "cmd": "python test.py {{test_size}}"}
  ]
}
```

### How It Works

1. **Menu displays variables**: Shows which tasks have `[⚙]` variables
2. **Selection triggers prompts**: After selecting a task, you're prompted for each variable
3. **Defaults offered**: Press Enter to use default values
4. **Substitution happens**: All `{{placeholders}}` replaced before execution

### Example Session

```bash
$ python run.py

  5. [✓] [⚙] template-codex
      1. Show directory
      2. Generate code via codex
      Variables: branch_name, repo_path, task_description
      Defaults: 3 provided

Selection: 5

================================================================================
TASK VARIABLES
================================================================================
branch_name [main]:
repo_path [/home/user/repo]: /home/user/myproject
task_description [create a function to calculate fibonacci]: create a sorting algorithm
================================================================================

Starting 1 task(s)...
```

### Template Use Cases

**1. Codex Workflows**
```json
{
  "name": "codex-template",
  "repo": "{{repo_path}}",
  "variables": {
    "repo_path": "/home/user/project",
    "feature_description": "add user authentication"
  },
  "steps": [
    {"desc": "Generate", "cmd": "codex exec -- \"{{feature_description}}\""}
  ]
}
```

**2. Multi-Environment Deployments**
```json
{
  "name": "deploy-template",
  "variables": {
    "environment": "staging",
    "region": "us-east-1"
  },
  "steps": [
    {"desc": "Deploy to {{environment}}", "cmd": "deploy.sh {{environment}} {{region}}"}
  ]
}
```

**3. Testing Different Configurations**
```json
{
  "name": "test-template",
  "variables": {
    "test_size": "1000",
    "algorithm": "quicksort"
  },
  "steps": [
    {"desc": "Test {{algorithm}}", "cmd": "python benchmark.py {{algorithm}} {{test_size}}"}
  ]
}
```

### Variable Features

- **Recursive substitution**: Variables work in all fields (repo, branch, steps, commands)
- **Default values**: Optional `variables` object provides defaults
- **Interactive prompts**: User-friendly prompting with `[default]` shown
- **Multiple variables**: Use as many as needed
- **No variables required**: Works with or without variables

## Git Worktree Support

Run tasks in isolated git worktrees for parallel workflows. Perfect for running multiple codex instances on the same repo simultaneously!

### What are Git Worktrees?

Git worktrees let you check out multiple branches/commits from the same repository in different directories. AIOS automatically creates, uses, and cleans up worktrees for your tasks.

### Worktree JSON Format

Add `repo` and optional `branch` fields to your task JSON:

```json
{
  "name": "codex-task",
  "repo": "/path/to/your/repo",
  "branch": "main",
  "steps": [
    {"desc": "Show directory", "cmd": "pwd"},
    {"desc": "Run codex", "cmd": "codex exec --sandbox workspace-write -- \"create hello.py\""},
    {"desc": "Show result", "cmd": "cat hello.py"}
  ]
}
```

### Worktree Location

Each task creates a worktree at:
```
jobs/<task-name-timestamp>/worktree/
```

Example:
```
jobs/codex-task-20251003_214513/worktree/
```

### Parallel Worktrees

Run multiple codex instances on the same repo simultaneously:

```bash
# Create two tasks
cat > task1.json <<EOF
{
  "name": "feature-1",
  "repo": "/home/user/myrepo",
  "branch": "main",
  "steps": [
    {"desc": "Generate code", "cmd": "codex exec -- \"implement feature 1\""}
  ]
}
EOF

cat > task2.json <<EOF
{
  "name": "feature-2",
  "repo": "/home/user/myrepo",
  "branch": "main",
  "steps": [
    {"desc": "Generate code", "cmd": "codex exec -- \"implement feature 2\""}
  ]
}
EOF

# Run both in parallel
./aios.py task1.json task2.json
```

Both tasks run in separate worktrees simultaneously - no conflicts!

### Worktree Cleanup

By default, worktrees are **NOT** automatically removed. This allows inspection after execution.

To manually clean up worktrees:
```bash
cd /path/to/your/repo
git worktree list
git worktree remove /path/to/worktree
```

### Testing Worktrees

Use the consolidated test script:

```bash
# List available tests
python test.py list

# Run worktree tests
python test.py run basic          # Basic worktree test
python test.py run codex          # Codex in worktree
python test.py run parallel       # Parallel worktrees
python test.py run parallel-codex # Parallel codex in worktrees

# Run all tests
python test.py all
```

## Job Output

### Output Location

All job output goes to `jobs/` directory:

```
jobs/
├── demo-20251003_203045/      # First run of 'demo' job
│   ├── test.txt
│   └── ...
├── demo-20251003_203152/      # Second run of 'demo' job
│   └── ...
└── deploy-20251003_203301/    # 'deploy' job
    └── ...
```

### Auto Cleanup

Automatically keeps the last 20 job directories and removes older ones after each job completes.

### View Job Output

```bash
# List all job outputs
ls jobs/

# View specific job output
cd jobs/demo-20251003_203045/
ls -la
```

## UI Layout

```
┌──────────────────────────────────────────┐
│  Status Display                          │  ← Updates every 0.5s
│  ┌────────────────────────────────────┐  │
│  │ Running Jobs:                      │  │
│  │   job1  | 2/3: Build  | ⟳ Running │  │
│  │   job2  | Done        | ✓ Done    │  │
│  │                                    │  │
│  │ Task Builder:                      │  │
│  │   job3:                            │  │
│  │     1. Create file                 │  │
│  │     2. Test file                   │  │
│  └────────────────────────────────────┘  │
├──────────────────────────────────────────┤
│  Output Messages                         │  ← Command feedback
│  ✓ Queued job: demo                      │
├──────────────────────────────────────────┤
│  ❯ your command here_                    │  ← Always stable
└──────────────────────────────────────────┘
```

## Status Colors

- **Yellow** (⟳ Running) - Job is executing
- **Green** (✓ Done) - Job completed successfully
- **Red** (✗ Error/Timeout) - Job failed

## Technical Details

### Architecture

- **prompt_toolkit** - Professional terminal UI (same library as IPython, pgcli)
- **libtmux** - Tmux session management
- **Threading** - 4 worker threads for parallel execution
- **Thread-safe** - Locks protect shared state

### Requirements

- Python 3.7+
- Real terminal (TTY) - won't work via pipes or background
- tmux installed

### Configuration

Edit these constants in `aios.py`:

```python
MAX_JOB_DIRS = 20    # Number of job directories to keep
```

Worker count (line ~271):
```python
workers = [Thread(target=worker, daemon=True) for _ in range(4)]  # 4 workers
```

Step timeout (line ~168):
```python
if not wait_ready(session_name, timeout=120):  # 120 seconds
```

## Troubleshooting

### "Input is not a terminal" error

You're running without a TTY (e.g., via pipe or background).

**Solution:** Run directly in a terminal:
```bash
./aios.py
```

Not via:
```bash
./aios.py < commands.txt  # ✗
./aios.py &               # ✗
echo "quit" | ./aios.py   # ✗
```

### Jobs stuck in "Running"

Check tmux sessions:
```bash
tmux ls | grep aios
```

Attach to a job's session:
```bash
tmux attach -t aios-demo-20251003_203045
```

Kill stuck session:
```bash
tmux kill-session -t aios-demo-20251003_203045
```

### UI looks broken

Ensure:
- Terminal is at least 80 characters wide
- Terminal supports 256 colors
- Using a modern terminal emulator

## Examples Included

- `test_task.json` - Simple 2-step example
- `example_task.json` - Codex factorization workflow
- `parallel_task.json` - Sorting algorithm example

Try them:
```bash
./aios.py test_task.json
```

## Similar Tools

This UI style is similar to:
- **IPython** - Interactive Python shell
- **k9s** - Kubernetes TUI
- **lazygit** - Git TUI
- **pgcli** - Postgres client
- **mycli** - MySQL client

All use prompt_toolkit for stable, professional terminal UIs.

## Why This Works

Previous approaches (rich.Live, ANSI codes) refreshed the screen and disrupted input.

**prompt_toolkit** solves this by:
1. Properly abstracting terminal handling
2. Separating UI components (status, output, input)
3. Event-driven updates that don't touch input
4. Professional-grade terminal management

Your input stays **rock solid** while status updates above!

## License

Open source - use freely for your projects.

## Credits

Built with:
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) - Terminal UI framework
- [libtmux](https://github.com/tmux-python/libtmux) - Tmux automation
