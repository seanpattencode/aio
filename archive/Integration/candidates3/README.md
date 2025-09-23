# Job Orchestrator Implementations

## 1. chatgpt2.py - All-in-One Scheduler & Executor (aiose)

### Installation
```bash
# No installation required, uses standard Python libraries
# For systemd support, ensure systemd is available
```

### Usage

#### Add a task
```bash
# Basic task
python3 chatgpt2.py add "echo 'Hello World'" --name my_task

# Task with arguments
python3 chatgpt2.py add "echo" "Hello" "World" --name greeting

# Task with priority and delay
python3 chatgpt2.py add "ls -la" --priority 10 --delay-ms 5000

# Systemd task with resource controls
python3 chatgpt2.py add "heavy_process" --mode systemd --cpu-weight 100 --mem-max-mb 512

# Scheduled task (systemd OnCalendar)
python3 chatgpt2.py add "backup.sh" --mode systemd --on-calendar "daily"

# Python function execution
python3 chatgpt2.py add "py:module.function" --mode py
```

#### Run worker
```bash
# Start worker (processes local/py tasks)
python3 chatgpt2.py worker

# Worker with custom batch size
python3 chatgpt2.py worker --batch 5 --idle-ms 100
```

#### Manage tasks
```bash
# List all tasks
python3 chatgpt2.py list

# Show statistics
python3 chatgpt2.py stats

# Start systemd task
python3 chatgpt2.py start task_name

# Stop systemd task
python3 chatgpt2.py stop task_name

# Check task status
python3 chatgpt2.py status task_name

# Reconcile systemd units
python3 chatgpt2.py reconcile

# Cleanup old tasks
python3 chatgpt2.py cleanup --days 7

# Install systemd service
python3 chatgpt2.py install > ~/.config/systemd/user/aiose-worker.service
systemctl --user daemon-reload
systemctl --user enable --now aiose-worker
```

## 2. claude2.py - Pure Python Job Orchestrator

### Installation
```bash
# No installation required for basic features
# Optional: pip install psutil  # For CPU affinity support
```

### Usage

#### Add a job
```bash
# Basic job with built-in function
python3 claude2.py add my_addition add --args 5 3

# Job with retry and timeout settings
python3 claude2.py add long_task long --args 30 --retries 5 --timeout 60

# Job with dependencies
python3 claude2.py add dependent_task process --depends 1 2 3

# Job with nice value
python3 claude2.py add low_priority_task add --args 1 1 --nice 10

# Delayed job
python3 claude2.py add delayed_task fail --delay 10
```

#### Run scheduler
```bash
# Start scheduler with default workers (CPU count)
python3 claude2.py scheduler

# Custom worker count
python3 claude2.py scheduler --workers 4 --batch 2
```

#### Load custom modules
```bash
# Load Python module with job functions
python3 claude2.py load /path/to/my_jobs.py
```

#### Manage jobs
```bash
# List all jobs
python3 claude2.py list

# List by status
python3 claude2.py list --status pending --limit 10

# Show statistics
python3 claude2.py stats

# Get job artifact
python3 claude2.py artifact 1 output_key

# Cleanup old jobs
python3 claude2.py cleanup --days 30
```

## 3. qwen2.py - Production Job Orchestrator with Systemd

### Installation
```bash
# Requires systemd
# Check if systemd-run is available
which systemd-run
```

### Usage

#### Add a task
```bash
# Basic task
python3 qwen2.py add my_task "echo" "Hello World"

# Task with priority
python3 qwen2.py add important_task "process_data.sh" -p 100

# Task with dependencies
python3 qwen2.py add final_task "cleanup.sh" --deps 1,2,3

# Task with resource limits
python3 qwen2.py add resource_limited "heavy_job" \
  --nice 10 \
  --cpu-weight 100 \
  --mem-max-mb 1024

# Scheduled task (systemd calendar format)
python3 qwen2.py add daily_backup "backup.sh" \
  --schedule "daily"

# Task with environment variables
python3 qwen2.py add env_task "script.py" \
  --env "PATH=/custom/path" \
  --env "DEBUG=true" \
  --cwd /home/user/workspace

# Real-time priority task
python3 qwen2.py add rt_task "realtime_process" --rtprio 50
```

#### Run worker
```bash
# Start worker (requires systemd)
python3 qwen2.py worker
```

#### Manage tasks
```bash
# Show statistics
python3 qwen2.py stats

# Cleanup old tasks
python3 qwen2.py cleanup --days 14
```

## Quick Comparison

| Feature | chatgpt2.py | claude2.py | qwen2.py |
|---------|-------------|------------|----------|
| Execution Modes | Local/Systemd/Python | Multiprocessing | Systemd only |
| Dependencies | ✓ | ✓ | ✓ |
| Scheduling | Systemd OnCalendar | Delay only | Systemd Calendar |
| Resource Limits | Systemd controls | Nice/CPU affinity | Full systemd |
| Retry Logic | ✓ | ✓ | ✓ |
| Artifacts Storage | ✗ | ✓ | ✗ |
| Lines of Code | ~440 | ~680 | ~450 |
| External Dependencies | None (systemd optional) | None (psutil optional) | systemd required |