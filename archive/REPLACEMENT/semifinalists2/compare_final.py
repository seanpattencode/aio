#!/usr/bin/env python3
"""
Final comprehensive benchmark of all implementations including claudeCodeB
"""

import time
import subprocess
import json
import sys
from pathlib import Path

def clean_db(impl):
    """Clean database before test"""
    dbs = {
        'claude1': 'aios_tasks.db',
        'claudeCode2': 'aios_scheduler.db',
        'ClaudeCodeA': 'aios_hybrid.db',
        'claudeCodeB': 'tasks_b.db'
    }
    if impl in dbs:
        db_path = Path(dbs[impl])
        if db_path.exists():
            db_path.unlink()

def benchmark_batch(name, cmds, iterations=100):
    """Run batch benchmark"""
    start = time.perf_counter()

    if isinstance(cmds, str):
        # Single command template
        for i in range(iterations):
            cmd = cmds.format(i=i)
            subprocess.run(cmd, shell=True, capture_output=True)
    else:
        # Multiple different commands
        for cmd in cmds[:iterations]:
            subprocess.run(cmd, shell=True, capture_output=True)

    elapsed = (time.perf_counter() - start) * 1000
    return elapsed, elapsed/iterations

def main():
    print("="*70)
    print("FINAL PERFORMANCE BENCHMARK - ALL IMPLEMENTATIONS")
    print("="*70)

    results = []

    # Test claudeCodeB
    print("\nTesting claudeCodeB...")
    clean_db('claudeCodeB')
    total, per = benchmark_batch(
        "claudeCodeB",
        "python3 claudeCodeB.py add 'echo test{i}' {i}"
    )
    results.append(("claudeCodeB", total, per))

    # Get stats
    stats_result = subprocess.run("python3 claudeCodeB.py stats",
                                shell=True, capture_output=True, text=True)
    print(f"  Stats: {stats_result.stdout.strip()}")

    # Test claude1
    print("\nTesting claude1.py...")
    clean_db('claude1')
    total, per = benchmark_batch(
        "claude1",
        "python3 claude1.py add-task 'task_{i}' 'echo test{i}' {i}"
    )
    results.append(("claude1.py", total, per))

    # Test claudeCode2
    print("\nTesting claudeCode2.py...")
    clean_db('claudeCode2')
    total, per = benchmark_batch(
        "claudeCode2",
        "python3 claudeCode2.py enqueue 'task_{i}' 'echo test{i}' {i}"
    )
    results.append(("claudeCode2.py", total, per))

    # Test ClaudeCodeA - Fast mode
    print("\nTesting ClaudeCodeA (FAST)...")
    clean_db('ClaudeCodeA')
    total, per = benchmark_batch(
        "ClaudeCodeA-FAST",
        "python3 ClaudeCodeA.py add --mode fast --name 'task_{i}' --cmd 'echo test{i}' --priority {i}"
    )
    results.append(("ClaudeCodeA-FAST", total, per))

    # Test ClaudeCodeA - Advanced mode
    print("\nTesting ClaudeCodeA (ADVANCED)...")
    total, per = benchmark_batch(
        "ClaudeCodeA-ADV",
        "python3 ClaudeCodeA.py add --mode advanced --name 'task_{i}' --cmd 'echo test{i}' --priority {i}",
        50  # Less iterations for advanced mode
    )
    results.append(("ClaudeCodeA-ADV", total, per))

    # Sort by performance
    results.sort(key=lambda x: x[2])

    # Print results
    print("\n" + "="*70)
    print("RESULTS (100 task insertions)")
    print("="*70)

    print(f"\n{'Rank':<6}{'Implementation':<20}{'Total (ms)':<15}{'Per Task (ms)':<15}{'vs Best'}")
    print("-"*70)

    best_time = results[0][2]
    for i, (name, total, per) in enumerate(results, 1):
        ratio = per / best_time if best_time > 0 else 1
        print(f"{i:<6}{name:<20}{total:<15.2f}{per:<15.4f}{ratio:.1f}x")

    print("\n" + "="*70)
    print(f"🏆 WINNER: {results[0][0]}")
    print(f"   Speed: {results[0][2]:.4f}ms per task")
    print(f"   {results[-1][2]/results[0][2]:.1f}x faster than slowest")
    print("="*70)

    # Additional metrics
    print("\n📊 Additional Metrics:")

    # Code size comparison
    implementations = {
        'claudeCodeB.py': Path('claudeCodeB.py'),
        'claude1.py': Path('claude1.py'),
        'claudeCode2.py': Path('claudeCode2.py'),
        'ClaudeCodeA.py': Path('ClaudeCodeA.py')
    }

    print("\nCode Size (lines):")
    for name, path in implementations.items():
        if path.exists():
            lines = len(path.read_text().splitlines())
            print(f"  {name:<20} {lines:>5} lines")

    # Feature comparison
    print("\nFeature Matrix:")
    features = {
        'claudeCodeB': '✓ Dependencies, ✓ Leasing, ✓ Retry, ✓ Batch, ✓ Systemd',
        'claude1': '✓ Retry, ✓ Systemd, ✗ Dependencies, ✗ Leasing',
        'claudeCode2': '✓ Dependencies, ✓ Leasing, ✓ Retry, ✓ Batch, ✓ Systemd',
        'ClaudeCodeA': '✓ ALL (Dual-mode)'
    }

    for impl, feat in features.items():
        print(f"  {impl:<15} {feat}")

if __name__ == "__main__":
    main()