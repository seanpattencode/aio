#!/usr/bin/env python3
import subprocess, time, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
RUNS = 5

tests = [
    ("Python", ["python3", "win.py", "echo", "x"]),
    ("C", ["./win_c", "/c", "echo", "x"]),
    ("ASM", ["./win_asm", "/c", "echo", "x"]),
]

print(f"Running {RUNS} iterations each...\n")
results = {}

for name, cmd in tests:
    times = []
    for _ in range(RUNS):
        start = time.perf_counter()
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        times.append((time.perf_counter() - start) * 1000)
    results[name] = {"avg": sum(times)/len(times), "min": min(times), "max": max(times)}

print(f"{'Version':<8} {'Avg':>8} {'Min':>8} {'Max':>8}")
print("-" * 36)
for name in ["Python", "C", "ASM"]:
    r = results[name]
    print(f"{name:<8} {r['avg']:>7.1f}ms {r['min']:>7.1f}ms {r['max']:>7.1f}ms")
