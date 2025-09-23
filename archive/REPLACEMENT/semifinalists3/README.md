# claudeCodeD Usage

## Installation
```bash
chmod +x claudeCodeD.py
```

## Commands

### Add Task
```bash
./claudeCodeD.py add "command" [priority] [delay_ms] [dependencies]

# Examples:
./claudeCodeD.py add "echo hello"                    # Default priority 0
./claudeCodeD.py add "python script.py" 10          # Priority 10
./claudeCodeD.py add "sleep 5" 5 1000               # Priority 5, delay 1 second
./claudeCodeD.py add "echo child" 0 0 "[1,2]"       # Depends on tasks 1 and 2
```

### Run Worker
```bash
./claudeCodeD.py worker [batch_size]

# Examples:
./claudeCodeD.py worker              # Process 1 task at a time
./claudeCodeD.py worker 10          # Process 10 tasks in batch
```

### Check Status
```bash
./claudeCodeD.py stats
```

### Clean Old Tasks
```bash
./claudeCodeD.py cleanup [days]

# Examples:
./claudeCodeD.py cleanup             # Clean tasks older than 7 days
./claudeCodeD.py cleanup 30          # Clean tasks older than 30 days
```

### Run Benchmark
```bash
./claudeCodeD.py bench
```

### Generate Systemd Service
```bash
./claudeCodeD.py systemd > claudecoded.service
sudo cp claudecoded.service /etc/systemd/system/
sudo systemctl enable claudecoded
sudo systemctl start claudecoded
```

## Database
Tasks are stored in `tasks_d.db` in the current directory.