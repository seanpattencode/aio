#!/usr/bin/env python3
"""Benchmark aio.py vs main_mod.py"""
import subprocess, time, os

os.chdir(os.path.dirname(__file__))

def bench(cmd, n=5):
    times = []
    for _ in range(n):
        s = time.time()
        subprocess.run(['python3'] + cmd, capture_output=True)
        times.append((time.time() - s) * 1000)
    return sum(times) / len(times)

# Commands to test (skip kill, pull, push, revert - destructive)
tests = [
    ('help', []),
    ('diff', []),
    ('update', []),
    ('copy', []),
]

print("=" * 60)
print(f"{'Command':<12} {'aio.py (ms)':<15} {'main_mod.py (ms)':<18} {'Δ':<10}")
print("=" * 60)

for cmd, args in tests:
    old = bench(['aio.py', cmd] + args)
    new = bench(['main_mod.py', cmd] + args)
    delta = ((new - old) / old) * 100
    print(f"{cmd:<12} {old:<15.1f} {new:<18.1f} {delta:+.0f}%")

print("=" * 60)
