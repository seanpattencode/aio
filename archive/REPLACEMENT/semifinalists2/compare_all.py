#!/usr/bin/env python3
"""
Comprehensive comparison of all SQLite task queue implementations
"""

import time
import subprocess
import json
import sys
from pathlib import Path

def benchmark_implementation(name, add_cmd_template, worker_cmd, stats_cmd=None):
    """Benchmark a single implementation"""
    print(f"\n=== Testing {name} ===")

    # Add tasks
    start = time.perf_counter()
    for i in range(10):
        cmd = add_cmd_template.format(i=i)
        subprocess.run(cmd, shell=True, capture_output=True)
    add_time = (time.perf_counter() - start) * 1000

    # Get stats if available
    if stats_cmd:
        result = subprocess.run(stats_cmd, shell=True, capture_output=True, text=True)
        try:
            stats = json.loads(result.stdout) if result.stdout else {}
        except:
            stats = {"raw": result.stdout}
    else:
        stats = {}

    return {
        "name": name,
        "add_time_ms": add_time,
        "per_task_ms": add_time / 10,
        "stats": stats
    }

def main():
    results = []

    # Test claude1.py
    results.append(benchmark_implementation(
        "claude1.py",
        "python3 claude1.py add-task 'task_{i}' 'echo test{i}'",
        "python3 claude1.py worker",
        "python3 claude1.py status"
    ))

    # Test claudeCode2.py
    results.append(benchmark_implementation(
        "claudeCode2.py",
        "python3 claudeCode2.py enqueue 'task_{i}' 'echo test{i}'",
        "python3 claudeCode2.py worker",
        "python3 claudeCode2.py stats"
    ))

    # Test ClaudeCodeA.py - Fast Mode
    results.append(benchmark_implementation(
        "ClaudeCodeA (FAST)",
        "python3 ClaudeCodeA.py add --mode fast --name 'task_{i}' --cmd 'echo test{i}'",
        "python3 ClaudeCodeA.py worker --mode fast",
        "python3 ClaudeCodeA.py stats --mode fast"
    ))

    # Test ClaudeCodeA.py - Advanced Mode
    results.append(benchmark_implementation(
        "ClaudeCodeA (ADVANCED)",
        "python3 ClaudeCodeA.py add --mode advanced --name 'task_{i}' --cmd 'echo test{i}'",
        "python3 ClaudeCodeA.py worker --mode advanced",
        "python3 ClaudeCodeA.py stats --mode advanced"
    ))

    # Print results
    print("\n\n" + "="*60)
    print("PERFORMANCE COMPARISON RESULTS")
    print("="*60)

    # Sort by performance
    results.sort(key=lambda x: x["per_task_ms"])

    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['name']}")
        print(f"   Total time (10 tasks): {result['add_time_ms']:.2f}ms")
        print(f"   Per task: {result['per_task_ms']:.3f}ms")
        if result['stats']:
            print(f"   Stats: {json.dumps(result['stats'], indent=6)}")

    print("\n" + "="*60)
    print("WINNER:", results[0]['name'])
    print(f"Speed advantage over slowest: {results[-1]['per_task_ms']/results[0]['per_task_ms']:.1f}x faster")
    print("="*60)

if __name__ == "__main__":
    main()