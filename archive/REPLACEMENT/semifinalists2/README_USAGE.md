# Usage Guide

## claude1.py
```bash
python3 claude1.py add-task "name" "command" [priority]
python3 claude1.py worker
python3 claude1.py status
```

## claudeCode2.py
```bash
python3 claudeCode2.py enqueue "name" "command" [priority] [delay]
python3 claudeCode2.py worker [batch_size]
python3 claudeCode2.py stats
```

## claudeCodeB.py
```bash
python3 claudeCodeB.py add "command" [priority]
python3 claudeCodeB.py worker [batch]
python3 claudeCodeB.py stats
```

## claudeCodeC_fixed.py
```bash
python3 claudeCodeC_fixed.py add "name" "command" [priority]
python3 claudeCodeC_fixed.py worker [batch]
python3 claudeCodeC_fixed.py stats
```

## claudeCodeCplus.py
```bash
python3 claudeCodeCplus.py add "command" [priority]
python3 claudeCodeCplus.py worker [batch]
python3 claudeCodeCplus.py stats
```

## claudeCodeD.py
```bash
python3 claudeCodeD.py add "command" [priority] [delay_ms] [deps_json]
python3 claudeCodeD.py worker [batch]
python3 claudeCodeD.py stats
python3 claudeCodeD.py cleanup [days]
```

## claudeCodeE.py
```bash
python3 claudeCodeE.py add "command" [priority] [deps_json]
python3 claudeCodeE.py worker [batch]
python3 claudeCodeE.py stats
```

## ClaudeCodeA.py
```bash
python3 ClaudeCodeA.py add --mode fast --name "name" --cmd "command" [--priority N]
python3 ClaudeCodeA.py add --mode advanced --name "name" --cmd "command" [--parent ID]
python3 ClaudeCodeA.py worker --mode fast [--batch N]
python3 ClaudeCodeA.py stats
```

## production_sqlite.py
```python
from production_sqlite import TaskQueue, Task, TaskWorker

queue = TaskQueue("tasks.db")
task = Task(type="job", payload={"key": "value"}, priority=10)
task_id = queue.enqueue(task)

worker = TaskWorker(queue, "worker-1")
worker.start()
```