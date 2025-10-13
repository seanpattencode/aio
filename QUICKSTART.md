# Quick Start Guide

## Install

```bash
pip install prompt_toolkit libtmux
```

## Run

```bash
./aios.py
```

You'll see a task menu at startup:

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

Enter task numbers to run them, or press Enter for interactive mode.

**[✓]** = Has git worktree support
**[ ]** = Regular task

## Try It

Once the UI loads, type these commands:

```
❯ demo: Create file | echo 'Hello World' > test.txt
❯ demo: Show file | cat test.txt
❯ run demo
```

Watch the status update above while your input stays stable!

## View Output

```bash
ls jobs/
cd jobs/demo-*
cat test.txt
```

## Exit

```
❯ quit
```

Or press `Ctrl+C`

## Load Tasks from JSON

```bash
./aios.py test_task.json
```

## Git Worktree Support

Run tasks in isolated git worktrees:

```bash
# Create a worktree task
cat > worktree_test.json <<EOF
{
  "name": "worktree-demo",
  "repo": "/path/to/your/repo",
  "branch": "main",
  "steps": [
    {"desc": "Show directory", "cmd": "pwd"},
    {"desc": "Show git status", "cmd": "git status"},
    {"desc": "Create file", "cmd": "echo 'test' > test.txt"}
  ]
}
EOF

# Run it
./aios.py worktree_test.json

# Or use the test script
python test.py run basic
```

### Parallel Codex in Worktrees

```bash
python test.py run parallel-codex
```

This runs two codex instances simultaneously in separate worktrees!

## Testing

```bash
# List all tests
python test.py list

# Run specific test
python test.py run codex

# Run all tests
python test.py all
```

See `README.md` for complete documentation.
