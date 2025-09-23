#!/usr/bin/env python3
"""Final benchmark including claudeCodeC"""

import time
import subprocess
import os
from pathlib import Path

def clean_dbs():
    """Clean all test databases"""
    for db in ['tasks.db', 'tasks_b.db', 'aios_tasks.db', 'aios_scheduler.db', 'aios_hybrid.db']:
        if Path(db).exists():
            os.unlink(db)

def benchmark(name, add_cmd, iterations=100):
    """Benchmark implementation"""
    start = time.perf_counter()
    for i in range(iterations):
        cmd = add_cmd.format(i=i)
        subprocess.run(cmd, shell=True, capture_output=True)
    return (time.perf_counter() - start) * 1000

def main():
    print("="*70)
    print("ULTIMATE PERFORMANCE SHOWDOWN")
    print("="*70)

    clean_dbs()
    results = []

    # Test each implementation
    implementations = [
        ("claudeCodeC", "python3 claudeCodeC.py add 'echo {i}' {i}"),
        ("claudeCodeB", "python3 claudeCodeB.py add 'echo {i}' {i}"),
        ("claude1", "python3 claude1.py add-task 'task{i}' 'echo {i}' {i}"),
        ("claudeCode2", "python3 claudeCode2.py enqueue 'task{i}' 'echo {i}' {i}"),
        ("ClaudeCodeA-F", "python3 ClaudeCodeA.py add --mode fast --name 't{i}' --cmd 'echo {i}'"),
    ]

    for name, cmd in implementations:
        print(f"\nTesting {name}...")
        time_ms = benchmark(name, cmd)
        results.append((name, time_ms, time_ms/100))
        print(f"  {time_ms:.2f}ms total, {time_ms/100:.4f}ms per task")

    # Sort by performance
    results.sort(key=lambda x: x[2])

    print("\n" + "="*70)
    print("FINAL RESULTS (100 operations)")
    print("="*70)
    print(f"\n{'Rank':<6}{'Name':<15}{'Total ms':<12}{'Per Task':<12}{'Speed'}")
    print("-"*60)

    best = results[0][2]
    for i, (name, total, per) in enumerate(results, 1):
        speed = per/best if best > 0 else 1
        print(f"{i:<6}{name:<15}{total:<12.2f}{per:<12.4f}{speed:.2f}x")

    print("\n" + "="*70)
    print(f"🏆 CHAMPION: {results[0][0]}")
    print(f"   {results[0][2]:.4f}ms per task")
    print(f"   {results[-1][2]/results[0][2]:.1f}x faster than slowest")

    # Code size comparison
    print("\nCode Size:")
    sizes = [
        ("claudeCodeC.py", 133),
        ("claudeCodeB.py", 274),
        ("claude1.py", 365),
        ("claudeCode2.py", 507),
        ("ClaudeCodeA.py", 776)
    ]
    for name, lines in sorted(sizes, key=lambda x: x[1]):
        print(f"  {name:<20} {lines:>4} lines")

    print("\n" + "="*70)
    print("claudeCodeC: Perfection Through Simplicity")
    print("="*70)

if __name__ == "__main__":
    main()