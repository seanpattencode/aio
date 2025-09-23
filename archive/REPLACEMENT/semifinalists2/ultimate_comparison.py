#!/usr/bin/env python3
"""
Ultimate comparison of all SQLite task queue implementations
"""

import time
import subprocess
import json
import os
from pathlib import Path

def clean_databases():
    """Clean all test databases"""
    for db in ['*.db']:
        os.system(f'rm -f {db}')

def benchmark_impl(name, file, add_pattern, iterations=100):
    """Benchmark an implementation"""
    print(f"\nTesting {name}...")

    # Clean database first
    os.system(f'rm -f *.db 2>/dev/null')

    start = time.perf_counter()
    for i in range(iterations):
        cmd = add_pattern.format(i=i)
        subprocess.run(cmd, shell=True, capture_output=True)
    elapsed = (time.perf_counter() - start) * 1000

    return {
        'name': name,
        'total_ms': elapsed,
        'per_op_ms': elapsed / iterations,
        'file': file
    }

def count_lines(file):
    """Count lines in file"""
    try:
        return len(Path(file).read_text().splitlines())
    except:
        return 0

def main():
    print("="*80)
    print("ULTIMATE SQLITE TASK QUEUE COMPARISON")
    print("="*80)

    implementations = [
        # Original minimalist versions
        ("claudeCodeC", "claudeCodeC.py",
         "python3 claudeCodeC.py add 'task{i}' 'echo {i}' {i}"),

        ("claudeCodeB", "claudeCodeB.py",
         "python3 claudeCodeB.py add 'echo {i}' {i}"),

        ("claude1", "claude1.py",
         "python3 claude1.py add-task 'task{i}' 'echo {i}' {i}"),

        ("claudeCode2", "claudeCode2.py",
         "python3 claudeCode2.py enqueue 'task{i}' 'echo {i}' {i}"),

        ("ClaudeCodeA", "ClaudeCodeA.py",
         "python3 ClaudeCodeA.py add --mode fast --name 't{i}' --cmd 'echo {i}'"),

        # New versions
        ("claudeCodeC+", "claudeCodeCplus.py",
         "python3 claudeCodeCplus.py add 'echo {i}' {i}"),

        ("claudeCodeD", "claudeCodeD.py",
         "python3 claudeCodeD.py add 'echo {i}' {i}"),
    ]

    results = []
    for name, file, pattern in implementations:
        if Path(file).exists():
            result = benchmark_impl(name, file, pattern)
            result['lines'] = count_lines(file)
            results.append(result)

    # Sort by performance
    results.sort(key=lambda x: x['per_op_ms'])

    # Display results
    print("\n" + "="*80)
    print("PERFORMANCE RESULTS (100 task insertions)")
    print("="*80)

    print(f"\n{'Rank':<6}{'Name':<15}{'Total ms':<12}{'Per Op':<12}{'Lines':<8}{'Efficiency'}")
    print("-"*75)

    best_perf = results[0]['per_op_ms']
    for i, r in enumerate(results, 1):
        speed_ratio = r['per_op_ms'] / best_perf
        efficiency = 1000 / (r['per_op_ms'] * r['lines']) if r['lines'] > 0 else 0
        print(f"{i:<6}{r['name']:<15}{r['total_ms']:<12.2f}{r['per_op_ms']:<12.4f}"
              f"{r['lines']:<8}{efficiency:<.4f}")

    print("\n" + "="*80)
    print("FEATURE COMPARISON")
    print("="*80)

    features = {
        'claudeCodeC': '✓ Minimal, ✓ Fast, ✓ Retry, ✗ Deps, ✗ Metrics',
        'claudeCodeB': '✓ Deps, ✓ Lease, ✓ Retry, ✓ Batch, ✗ Metrics',
        'claude1': '✓ Systemd, ✓ Retry, ✗ Deps, ✗ Metrics',
        'claudeCode2': '✓ Full features, ✓ Deps, ✓ Lease, ✗ Simple',
        'ClaudeCodeA': '✓ Dual-mode, ✓ All features, ✗ Complex',
        'claudeCodeC+': '✓ Minimal, ✓ Safe pop, ✓ WAL, ✓ Retry',
        'claudeCodeD': '✓ Deps, ✓ Metrics, ✓ Fast, ✓ Production'
    }

    for name, feat in features.items():
        if any(r['name'] == name for r in results):
            print(f"  {name:<15} {feat}")

    # Special benchmarks for top performers
    print("\n" + "="*80)
    print("ADVANCED BENCHMARKS (Top 3)")
    print("="*80)

    for impl in results[:3]:
        name = impl['name']
        file = impl['file']

        if name == 'claudeCodeD':
            print(f"\n{name}:")
            result = subprocess.run("python3 claudeCodeD.py bench",
                                  shell=True, capture_output=True, text=True)
            for line in result.stdout.split('\n')[1:6]:
                if line.strip():
                    print(f"  {line}")

        elif name == 'claudeCodeC+':
            print(f"\n{name}:")
            result = subprocess.run("python3 claudeCodeCplus.py bench",
                                  shell=True, capture_output=True, text=True)
            for line in result.stdout.split('\n')[1:4]:
                if line.strip():
                    print(f"  {line}")

        elif name == 'claudeCodeC':
            print(f"\n{name}:")
            result = subprocess.run("python3 claudeCodeC.py bench",
                                  shell=True, capture_output=True, text=True)
            for line in result.stdout.split('\n')[:3]:
                if line.strip():
                    print(f"  {line}")

    print("\n" + "="*80)
    print(f"🏆 WINNER: {results[0]['name']}")
    print(f"   Speed: {results[0]['per_op_ms']:.4f}ms per operation")
    print(f"   Code: {results[0]['lines']} lines")
    print(f"   {results[-1]['per_op_ms']/results[0]['per_op_ms']:.1f}x faster than slowest")
    print("="*80)

    # Analysis summary
    print("\n📊 ANALYSIS SUMMARY:")
    print(f"""
1. SPEED CHAMPION: {results[0]['name']} ({results[0]['per_op_ms']:.4f}ms/op)
2. SMALLEST CODE: {min(results, key=lambda x: x['lines'])['name']} ({min(results, key=lambda x: x['lines'])['lines']} lines)
3. BEST EFFICIENCY: {max(results, key=lambda x: 1000/(x['per_op_ms']*x['lines']))['name']}
4. MOST FEATURES: claudeCodeD (deps, metrics, production pragmas)

RECOMMENDATIONS:
- Ultra-fast simple tasks: {results[0]['name']}
- Production with monitoring: claudeCodeD
- Minimal deployment: claudeCodeC or claudeCodeC+
""")

if __name__ == "__main__":
    main()