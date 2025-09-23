#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from production_sqlite import TaskQueue, Task, TaskPriority
import time
import json
import os

# Remove existing test DB
if os.path.exists("test_prod.db"):
    os.unlink("test_prod.db")

# Create test queue
queue = TaskQueue("test_prod.db")

# Test basic operations
print("Testing basic operations...")

# Add some tasks
task1 = Task(type="test", payload={"msg": "hello"}, priority=10)
task_id1 = queue.enqueue(task1)
print(f"Added task {task_id1}")

task2 = Task(type="test", payload={"msg": "world"}, priority=5)
task_id2 = queue.enqueue(task2)
print(f"Added task {task_id2}")

# Check metrics
metrics = queue.get_metrics()
print(f"Initial metrics: {json.dumps(metrics, indent=2)}")

# Dequeue a task
task = queue.dequeue("worker1")
if task:
    print(f"Dequeued task {task.id} with priority {task.priority}")
    queue.complete_task(task.id, {"success": True})
    print(f"Completed task {task.id}")

# Final metrics
metrics = queue.get_metrics()
print(f"Final metrics: {json.dumps(metrics, indent=2)}")
