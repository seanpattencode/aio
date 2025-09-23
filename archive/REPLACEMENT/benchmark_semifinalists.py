#!/usr/bin/env python3
"""
Comprehensive benchmark of all semifinalist implementations
"""

import time
import sys
import os
import json
from pathlib import Path

# Results storage
results = {}

def benchmark_claude1():
    """Test claude1 - Ultra minimal, high performance"""
    from claude1 import SystemdOrchestrator

    print("\n=== Benchmarking claude1.py (Ultra-minimal) ===")
    orch = SystemdOrchestrator()

    # Test 1: Add tasks
    start = time.perf_counter()
    for i in range(100):
        orch.task_queue.push(f'test_{i}', f'echo {i}', i % 10)
    add_time = (time.perf_counter() - start) * 1000

    # Test 2: Pop tasks
    start = time.perf_counter()
    for _ in range(50):
        task = orch.task_queue.pop()
    pop_time = (time.perf_counter() - start) * 1000

    # Test 3: Complete tasks
    start = time.perf_counter()
    for i in range(1, 26):
        orch.task_queue.complete(i, True, 'done')
    complete_time = (time.perf_counter() - start) * 1000

    stats = orch.task_queue.get_stats()

    return {
        'add_per_task_ms': add_time / 100,
        'pop_per_task_ms': pop_time / 50,
        'complete_per_task_ms': complete_time / 25,
        'total_time_ms': add_time + pop_time + complete_time,
        'features': ['atomic_ops', 'minimal', 'systemd', 'retry'],
        'complexity': 'low',
        'final_stats': stats
    }

def benchmark_claudeCode2():
    """Test claudeCode2 - Advanced scheduling"""
    from claudeCode2 import AdvancedTaskQueue

    print("\n=== Benchmarking claudeCode2.py (Advanced Scheduling) ===")
    queue = AdvancedTaskQueue()

    # Test 1: Enqueue tasks
    start = time.perf_counter()
    for i in range(100):
        queue.enqueue(f'test_{i}', f'echo {i}', priority=i % 10)
    add_time = (time.perf_counter() - start) * 1000

    # Test 2: Claim tasks
    start = time.perf_counter()
    claimed = []
    for _ in range(10):
        tasks = queue.claim_tasks('worker1', 5)
        claimed.extend(tasks)
    claim_time = (time.perf_counter() - start) * 1000

    # Test 3: Complete tasks
    start = time.perf_counter()
    for i, task in enumerate(claimed[:25]):
        run_id = queue.start_task(task.id, 'worker1')
        queue.complete_task(task.id, run_id, i % 2 == 0)
    complete_time = (time.perf_counter() - start) * 1000

    stats = queue.get_stats()

    return {
        'add_per_task_ms': add_time / 100,
        'claim_per_batch_ms': claim_time / 10,
        'complete_per_task_ms': complete_time / 25,
        'total_time_ms': add_time + claim_time + complete_time,
        'features': ['leasing', 'dependencies', 'backoff', 'distributed'],
        'complexity': 'high',
        'final_stats': stats
    }

def benchmark_claudeCode3():
    """Test claudeCode3 - Event-driven"""
    from claudeCode3 import EventDrivenOrchestrator

    print("\n=== Benchmarking claudeCode3.py (Event-driven) ===")
    orch = EventDrivenOrchestrator()
    orch.start()

    # Test 1: Create tasks
    start = time.perf_counter()
    for i in range(100):
        orch.event_store.publish(
            EventType.TASK_CREATED,
            f'task_{i}', 'task',
            {'name': f'test_{i}', 'command': f'echo {i}'}
        )
    add_time = (time.perf_counter() - start) * 1000

    # Test 2: Process events
    start = time.perf_counter()
    orch.event_store._process_unprocessed()
    process_time = (time.perf_counter() - start) * 1000

    # Test 3: Execute tasks
    start = time.perf_counter()
    count = 0
    for task_id, state in list(orch.state_machine.states.items())[:25]:
        if state.status == 'pending':
            orch.execute_task(task_id)
            count += 1
    exec_time = (time.perf_counter() - start) * 1000

    orch.stop()

    return {
        'add_per_event_ms': add_time / 100,
        'process_time_ms': process_time,
        'execute_per_task_ms': exec_time / max(count, 1),
        'total_time_ms': add_time + process_time + exec_time,
        'features': ['event_sourcing', 'state_machine', 'workflows', 'replay'],
        'complexity': 'very_high',
        'tasks_executed': count
    }

def benchmark_claudeCode4():
    """Test claudeCode4 - Production system"""
    from claudeCode4 import ProductionOrchestrator

    print("\n=== Benchmarking claudeCode4.py (Production System) ===")
    orch = ProductionOrchestrator()
    orch.start()

    # Test 1: Add tasks
    start = time.perf_counter()
    for i in range(100):
        orch.queue.add_task(f'test_{i}', f'echo {i}', priority=i % 10)
    add_time = (time.perf_counter() - start) * 1000

    # Test 2: Get tasks
    start = time.perf_counter()
    tasks = []
    for _ in range(50):
        task = orch.queue.get_next_task('worker1')
        if task:
            tasks.append(task)
    get_time = (time.perf_counter() - start) * 1000

    # Test 3: Complete tasks
    start = time.perf_counter()
    for task in tasks[:25]:
        orch.queue.complete_task(task['id'], True, 'done', 10, 50.0)
    complete_time = (time.perf_counter() - start) * 1000

    # Get metrics
    metrics = orch.metrics.get_summary()
    health = orch.health_checker.run_checks()

    orch.stop()

    return {
        'add_per_task_ms': add_time / 100,
        'get_per_task_ms': get_time / 50,
        'complete_per_task_ms': complete_time / 25,
        'total_time_ms': add_time + get_time + complete_time,
        'features': ['web_ui', 'metrics', 'health_checks', 'alerts', 'monitoring'],
        'complexity': 'very_high',
        'health_checks': list(health.keys()),
        'metrics_types': len(metrics.get('counters', {}))
    }

def benchmark_deepseek2():
    """Test deepseek2 - Systemd integrated"""
    from deepseek2 import AIOSTaskQueue

    print("\n=== Benchmarking deepseek2.py (Systemd Integrated) ===")
    queue = AIOSTaskQueue()

    # Test 1: Add tasks
    start = time.perf_counter()
    for i in range(100):
        queue.add_task(f'test_{i}', f'echo {i}', priority=i % 5)
    add_time = (time.perf_counter() - start) * 1000

    # Test 2: Get tasks
    start = time.perf_counter()
    tasks = []
    for _ in range(50):
        task = queue.get_next_task()
        if task:
            tasks.append(task)
    get_time = (time.perf_counter() - start) * 1000

    # Test 3: Update tasks
    start = time.perf_counter()
    for i, task in enumerate(tasks[:25]):
        from deepseek2 import TaskStatus
        queue.update_task(task.id, TaskStatus.COMPLETED, result='done')
    update_time = (time.perf_counter() - start) * 1000

    stats = queue.get_stats()

    return {
        'add_per_task_ms': add_time / 100,
        'get_per_task_ms': get_time / 50,
        'update_per_task_ms': update_time / 25,
        'total_time_ms': add_time + get_time + update_time,
        'features': ['systemd', 'resource_tracking', 'cleanup', 'monitoring'],
        'complexity': 'medium',
        'final_stats': stats
    }

def main():
    print("=" * 60)
    print("SEMIFINALIST BENCHMARK SUITE")
    print("=" * 60)

    # Run benchmarks
    try:
        results['claude1'] = benchmark_claude1()
    except Exception as e:
        print(f"Error benchmarking claude1: {e}")
        results['claude1'] = {'error': str(e)}

    try:
        results['claudeCode2'] = benchmark_claudeCode2()
    except Exception as e:
        print(f"Error benchmarking claudeCode2: {e}")
        results['claudeCode2'] = {'error': str(e)}

    try:
        from claudeCode3 import EventType
        results['claudeCode3'] = benchmark_claudeCode3()
    except Exception as e:
        print(f"Error benchmarking claudeCode3: {e}")
        results['claudeCode3'] = {'error': str(e)}

    try:
        results['claudeCode4'] = benchmark_claudeCode4()
    except Exception as e:
        print(f"Error benchmarking claudeCode4: {e}")
        results['claudeCode4'] = {'error': str(e)}

    try:
        results['deepseek2'] = benchmark_deepseek2()
    except Exception as e:
        print(f"Error benchmarking deepseek2: {e}")
        results['deepseek2'] = {'error': str(e)}

    # Analysis
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS SUMMARY")
    print("=" * 60)

    # Performance ranking
    perf_scores = []
    for name, data in results.items():
        if 'error' not in data:
            score = data.get('total_time_ms', float('inf'))
            perf_scores.append((name, score, data))

    perf_scores.sort(key=lambda x: x[1])

    print("\n### Performance Ranking (by total time):")
    for i, (name, score, data) in enumerate(perf_scores, 1):
        print(f"{i}. {name}: {score:.2f}ms total")
        print(f"   - Add: {data.get('add_per_task_ms', 0):.3f}ms/task")
        print(f"   - Complexity: {data.get('complexity', 'unknown')}")
        print(f"   - Features: {', '.join(data.get('features', [])[:3])}")

    # Feature analysis
    print("\n### Feature Analysis:")
    for name, data in results.items():
        if 'error' not in data:
            features = data.get('features', [])
            print(f"{name}: {len(features)} features - {', '.join(features[:3])}")

    # Recommendations
    print("\n### FINAL RANKINGS:")
    print("\n1. PERFORMANCE WINNERS (Top 2 excluding deepseek2):")

    # Get non-deepseek2 implementations
    non_deepseek = [x for x in perf_scores if x[0] != 'deepseek2']

    if len(non_deepseek) >= 2:
        print(f"   🥇 {non_deepseek[0][0]} - Fastest overall ({non_deepseek[0][1]:.2f}ms)")
        print(f"   🥈 {non_deepseek[1][0]} - Second fastest ({non_deepseek[1][1]:.2f}ms)")

        # Weakest 3 (excluding deepseek2)
        print("\n2. IMPLEMENTATIONS TO CUT (Weakest 3):")
        for i, (name, score, data) in enumerate(non_deepseek[-3:], 1):
            print(f"   {i}. {name} - {score:.2f}ms (Complexity: {data.get('complexity', 'unknown')})")

    return results

if __name__ == "__main__":
    main()