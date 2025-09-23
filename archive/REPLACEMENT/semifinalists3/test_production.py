#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from production_sqlite import TaskQueue, Task, TaskPriority
import time
import json

# Create test queue
queue = TaskQueue("test_prod.db")

# Test 1: Simple inserts benchmark
start = time.perf_counter()
for i in range(1000):
    task = Task(type="test", payload={"index": i}, priority=i % 10)
    queue.enqueue(task)
t1 = (time.perf_counter() - start) * 1000

# Test 2: With dependencies
start = time.perf_counter()
parent_task = Task(type="parent", payload={"msg": "parent"}, priority=10)
parent_id = queue.enqueue(parent_task)
for i in range(100):
    child_task = Task(type="child", payload={"index": i}, priority=5, dependencies=[parent_id])
    queue.enqueue(child_task)
t2 = (time.perf_counter() - start) * 1000

# Test 3: Dequeues (pops)
start = time.perf_counter()
for _ in range(100):
    task = queue.dequeue("test_worker")
    if not task:
        break
t3 = (time.perf_counter() - start) * 1000

# Test 4: Completions
start = time.perf_counter()
for i in range(1, 51):
    queue.complete_task(i, {"test": "result"})
t4 = (time.perf_counter() - start) * 1000

# Get metrics
metrics = queue.get_metrics()

print(f"""
=== production_sqlite Performance ===
1000 inserts:      {t1:.2f}ms ({t1/1000:.4f}ms/op)
101 w/deps:        {t2:.2f}ms ({t2/101:.4f}ms/op)
100 dequeues:      {t3:.2f}ms ({t3/100:.4f}ms/op)
50 completions:    {t4:.2f}ms ({t4/50:.4f}ms/op)

Metrics: {json.dumps(metrics, indent=2)}
""")
