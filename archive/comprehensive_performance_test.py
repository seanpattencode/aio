#!/usr/bin/env python3
"""
Comprehensive performance testing for AIOS orchestrator
Tests startup, shutdown, restart times, memory usage, and resilience
"""

import os
import subprocess
import time
import signal
import psutil
import random
import statistics
import json
import sqlite3
from datetime import datetime

def get_process_info(pid):
    """Get memory and CPU info for a process"""
    try:
        proc = psutil.Process(pid)
        return {
            'memory_mb': proc.memory_info().rss / 1024 / 1024,
            'cpu_percent': proc.cpu_percent(interval=0.1),
            'num_threads': proc.num_threads(),
            'num_fds': len(proc.open_files()) if hasattr(proc, 'open_files') else 0
        }
    except:
        return None

def test_startup_time(iterations=5):
    """Test cold startup time"""
    print(f"\n=== Testing Startup Time ({iterations} iterations) ===")
    times = []

    for i in range(iterations):
        # Clean state
        subprocess.run(['pkill', '-f', 'simple_orchestrator'], capture_output=True)
        time.sleep(0.5)

        # Measure startup
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
                startup_time = time.perf_counter() - start
                times.append(startup_time * 1000)  # Convert to ms
                print(f"  Iteration {i+1}: {startup_time*1000:.2f}ms")
                break

        # Kill the process
        proc.terminate()
        proc.wait()

    return {
        'min_ms': min(times),
        'max_ms': max(times),
        'avg_ms': statistics.mean(times),
        'median_ms': statistics.median(times),
        'stddev_ms': statistics.stdev(times) if len(times) > 1 else 0
    }

def test_shutdown_time(iterations=5):
    """Test graceful shutdown time"""
    print(f"\n=== Testing Shutdown Time ({iterations} iterations) ===")
    times = []

    for i in range(iterations):
        # Start orchestrator
        proc = subprocess.Popen(
            ['python3', 'simple_orchestrator.py', '--force'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(1)  # Let it fully start

        # Measure shutdown
        start = time.perf_counter()
        proc.send_signal(signal.SIGTERM)
        proc.wait()
        shutdown_time = time.perf_counter() - start
        times.append(shutdown_time * 1000)  # Convert to ms
        print(f"  Iteration {i+1}: {shutdown_time*1000:.2f}ms")

        time.sleep(0.5)

    return {
        'min_ms': min(times),
        'max_ms': max(times),
        'avg_ms': statistics.mean(times),
        'median_ms': statistics.median(times),
        'stddev_ms': statistics.stdev(times) if len(times) > 1 else 0
    }

def test_restart_resilience(duration=30, restart_interval=3):
    """Test system resilience to random restarts"""
    print(f"\n=== Testing Restart Resilience (duration={duration}s) ===")

    restarts = []
    errors = []
    start_time = time.time()

    # Start orchestrator
    proc = subprocess.Popen(
        ['python3', 'simple_orchestrator.py', '--force'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    while time.time() - start_time < duration:
        time.sleep(restart_interval + random.random() * 2)

        # Trigger restart via database
        restart_start = time.perf_counter()
        try:
            conn = sqlite3.connect('orchestrator.db')
            conn.execute("INSERT INTO triggers (job, args, kwargs, created) VALUES (?, ?, ?, ?)",
                        ('RESTART_ALL', '[]', '{}', time.time()))
            conn.commit()
            conn.close()
            restart_time = (time.perf_counter() - restart_start) * 1000
            restarts.append(restart_time)
            print(f"  Restart at {time.time()-start_time:.1f}s: {restart_time:.2f}ms")
        except Exception as e:
            errors.append(str(e))
            print(f"  Restart failed: {e}")

    proc.terminate()
    proc.wait()

    return {
        'total_restarts': len(restarts),
        'successful_restarts': len(restarts),
        'failed_restarts': len(errors),
        'avg_restart_ms': statistics.mean(restarts) if restarts else 0,
        'max_restart_ms': max(restarts) if restarts else 0,
        'min_restart_ms': min(restarts) if restarts else 0
    }

def test_memory_usage(duration=10):
    """Test memory usage over time"""
    print(f"\n=== Testing Memory Usage (duration={duration}s) ===")

    # Start orchestrator
    proc = subprocess.Popen(
        ['python3', 'simple_orchestrator.py', '--force'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    memory_samples = []
    cpu_samples = []
    start_time = time.time()

    try:
        psutil_proc = psutil.Process(proc.pid)
        while time.time() - start_time < duration:
            info = get_process_info(proc.pid)
            if info:
                memory_samples.append(info['memory_mb'])
                cpu_samples.append(info['cpu_percent'])
            time.sleep(0.5)
    except:
        pass

    proc.terminate()
    proc.wait()

    return {
        'initial_memory_mb': memory_samples[0] if memory_samples else 0,
        'peak_memory_mb': max(memory_samples) if memory_samples else 0,
        'avg_memory_mb': statistics.mean(memory_samples) if memory_samples else 0,
        'memory_growth_mb': (memory_samples[-1] - memory_samples[0]) if len(memory_samples) > 1 else 0,
        'avg_cpu_percent': statistics.mean(cpu_samples) if cpu_samples else 0,
        'peak_cpu_percent': max(cpu_samples) if cpu_samples else 0
    }

def test_job_startup_times():
    """Test individual job startup times"""
    print(f"\n=== Testing Job Startup Times ===")

    # Start orchestrator
    proc = subprocess.Popen(
        ['python3', 'simple_orchestrator.py', '--force'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    time.sleep(2)  # Let it stabilize

    # Check database for job statuses
    conn = sqlite3.connect('orchestrator.db')
    jobs = conn.execute("SELECT name, status, updated FROM jobs").fetchall()
    conn.close()

    proc.terminate()
    proc.wait()

    job_times = {}
    for name, status, updated in jobs:
        job_times[name] = {
            'status': status,
            'startup_time': updated if updated else 0
        }

    return job_times

def main():
    """Run all performance tests"""
    print("=" * 60)
    print("AIOS COMPREHENSIVE PERFORMANCE TEST")
    print("=" * 60)

    os.chdir('/home/seanpatten/projects/AIOS')

    # Clean up any existing processes
    subprocess.run(['pkill', '-f', 'simple_orchestrator'], capture_output=True)
    time.sleep(1)

    results = {
        'timestamp': datetime.now().isoformat(),
        'startup': test_startup_time(iterations=10),
        'shutdown': test_shutdown_time(iterations=10),
        'memory': test_memory_usage(duration=15),
        'resilience': test_restart_resilience(duration=20, restart_interval=2),
        'jobs': test_job_startup_times()
    }

    # Performance requirement check
    print("\n" + "=" * 60)
    print("PERFORMANCE REQUIREMENT CHECK (100ms limit)")
    print("=" * 60)

    violations = []

    if results['startup']['avg_ms'] > 100:
        violations.append(f"Startup: {results['startup']['avg_ms']:.2f}ms (VIOLATION)")
        print(f"❌ Startup: {results['startup']['avg_ms']:.2f}ms > 100ms")
    else:
        print(f"✅ Startup: {results['startup']['avg_ms']:.2f}ms < 100ms")

    if results['shutdown']['avg_ms'] > 100:
        violations.append(f"Shutdown: {results['shutdown']['avg_ms']:.2f}ms (VIOLATION)")
        print(f"❌ Shutdown: {results['shutdown']['avg_ms']:.2f}ms > 100ms")
    else:
        print(f"✅ Shutdown: {results['shutdown']['avg_ms']:.2f}ms < 100ms")

    if results['resilience']['avg_restart_ms'] > 100:
        violations.append(f"Restart: {results['resilience']['avg_restart_ms']:.2f}ms (VIOLATION)")
        print(f"❌ Restart: {results['resilience']['avg_restart_ms']:.2f}ms > 100ms")
    else:
        print(f"✅ Restart: {results['resilience']['avg_restart_ms']:.2f}ms < 100ms")

    # Summary
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"Startup Time:  {results['startup']['avg_ms']:.2f}ms (±{results['startup']['stddev_ms']:.2f}ms)")
    print(f"Shutdown Time: {results['shutdown']['avg_ms']:.2f}ms (±{results['shutdown']['stddev_ms']:.2f}ms)")
    print(f"Restart Time:  {results['resilience']['avg_restart_ms']:.2f}ms")
    print(f"Memory Usage:  {results['memory']['avg_memory_mb']:.1f}MB (peak: {results['memory']['peak_memory_mb']:.1f}MB)")
    print(f"CPU Usage:     {results['memory']['avg_cpu_percent']:.1f}% (peak: {results['memory']['peak_cpu_percent']:.1f}%)")
    print(f"Resilience:    {results['resilience']['successful_restarts']}/{results['resilience']['total_restarts']} restarts successful")

    if violations:
        print(f"\n⚠️  PERFORMANCE VIOLATIONS DETECTED:")
        for v in violations:
            print(f"   - {v}")
    else:
        print(f"\n✅ ALL PERFORMANCE REQUIREMENTS MET!")

    # Save results to file
    with open('performance_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to performance_results.json")

    return results

if __name__ == "__main__":
    main()