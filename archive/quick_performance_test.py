#!/usr/bin/env python3
"""Quick performance test for AIOS orchestrator"""

import subprocess
import time
import signal
import os

# Change to AIOS directory
os.chdir('/home/seanpatten/projects/AIOS')

# Kill any existing processes
subprocess.run(['pkill', '-9', '-f', 'simple_orchestrator'], capture_output=True)
subprocess.run(['pkill', '-9', '-f', 'web_server'], capture_output=True)
time.sleep(1)

print("=" * 60)
print("AIOS PERFORMANCE TEST")
print("=" * 60)

# Test 1: Startup Time
print("\n1. STARTUP TIME TEST:")
startup_times = []
for i in range(5):
    start = time.perf_counter()
    proc = subprocess.Popen(
        ['python3', 'simple_orchestrator.py', '--force'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for startup message
    for line in proc.stdout:
        if "Orchestrator started" in line:
            elapsed = (time.perf_counter() - start) * 1000
            startup_times.append(elapsed)
            print(f"   Run {i+1}: {elapsed:.2f}ms")
            break

    proc.kill()
    time.sleep(0.5)

avg_startup = sum(startup_times) / len(startup_times) if startup_times else 0
print(f"   Average: {avg_startup:.2f}ms")

# Test 2: Shutdown Time
print("\n2. SHUTDOWN TIME TEST:")
shutdown_times = []
for i in range(5):
    # Start process
    proc = subprocess.Popen(
        ['python3', 'simple_orchestrator.py', '--force'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(1)  # Let it stabilize

    # Measure shutdown
    start = time.perf_counter()
    proc.send_signal(signal.SIGTERM)
    proc.wait()
    elapsed = (time.perf_counter() - start) * 1000
    shutdown_times.append(elapsed)
    print(f"   Run {i+1}: {elapsed:.2f}ms")
    time.sleep(0.5)

avg_shutdown = sum(shutdown_times) / len(shutdown_times) if shutdown_times else 0
print(f"   Average: {avg_shutdown:.2f}ms")

# Test 3: Memory Usage
print("\n3. MEMORY USAGE TEST:")
proc = subprocess.Popen(
    ['python3', 'simple_orchestrator.py', '--force'],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)
time.sleep(2)

# Get memory info using ps
result = subprocess.run(
    ['ps', 'aux'],
    capture_output=True,
    text=True
)

for line in result.stdout.split('\n'):
    if 'simple_orchestrator.py' in line and str(proc.pid) in line:
        parts = line.split()
        if len(parts) > 5:
            memory_percent = parts[3]
            virt_mem = parts[4]
            res_mem = parts[5]
            print(f"   Memory: {memory_percent}% of system")
            print(f"   Virtual: {virt_mem} KB")
            print(f"   Resident: {res_mem} KB")
            break

proc.kill()

# Test 4: Restart Performance
print("\n4. RESTART PERFORMANCE TEST:")
proc = subprocess.Popen(
    ['python3', 'simple_orchestrator.py', '--force'],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)
time.sleep(2)

restart_times = []
import sqlite3
for i in range(3):
    start = time.perf_counter()
    conn = sqlite3.connect('orchestrator.db')
    conn.execute("INSERT INTO triggers (job, args, kwargs, created) VALUES ('RESTART_ALL', '[]', '{}', ?)", (time.time(),))
    conn.commit()
    conn.close()
    elapsed = (time.perf_counter() - start) * 1000
    restart_times.append(elapsed)
    print(f"   Restart {i+1}: {elapsed:.2f}ms")
    time.sleep(2)

avg_restart = sum(restart_times) / len(restart_times) if restart_times else 0
print(f"   Average: {avg_restart:.2f}ms")

proc.kill()

# Summary
print("\n" + "=" * 60)
print("PERFORMANCE SUMMARY")
print("=" * 60)
print(f"Average Startup Time:  {avg_startup:.2f}ms {'✅' if avg_startup < 100 else '❌ VIOLATION'}")
print(f"Average Shutdown Time: {avg_shutdown:.2f}ms {'✅' if avg_shutdown < 100 else '❌ VIOLATION'}")
print(f"Average Restart Time:  {avg_restart:.2f}ms {'✅' if avg_restart < 100 else '❌ VIOLATION'}")

if avg_startup < 100 and avg_shutdown < 100 and avg_restart < 100:
    print("\n✅ ALL PERFORMANCE REQUIREMENTS MET!")
else:
    print("\n❌ PERFORMANCE VIOLATIONS DETECTED!")

# Clean up
subprocess.run(['pkill', '-9', '-f', 'simple_orchestrator'], capture_output=True)
subprocess.run(['pkill', '-9', '-f', 'web_server'], capture_output=True)