#!/usr/bin/env python3
"""Benchmark raw write syscall from within running process"""
import os
import time

msg = b"Hello, World!\n"
runs = 1000

# Warmup
for _ in range(10):
    os.write(1, msg)

# Redirect stdout to /dev/null
devnull = os.open("/dev/null", os.O_WRONLY)
os.dup2(devnull, 1)

times = []
for _ in range(runs):
    start = time.perf_counter_ns()
    os.write(1, msg)
    end = time.perf_counter_ns()
    times.append(end - start)

os.close(devnull)

min_ns = min(times)
max_ns = max(times)
avg_ns = sum(times) // len(times)

print(f"\n=== os.write() syscall benchmark (Python) ===", file=__import__('sys').stderr)
print(f"Runs: {runs}", file=__import__('sys').stderr)
print(f"Min:  {min_ns} ns ({min_ns/1000000:.3f} ms)", file=__import__('sys').stderr)
print(f"Max:  {max_ns} ns ({max_ns/1000000:.3f} ms)", file=__import__('sys').stderr)
print(f"Avg:  {avg_ns} ns ({avg_ns/1000000:.3f} ms)", file=__import__('sys').stderr)
