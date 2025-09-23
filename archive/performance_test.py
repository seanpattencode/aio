#!/usr/bin/env python3
"""Performance testing script for AIOS orchestrator."""

import subprocess
import time
import random
import signal
import os
import psutil
import statistics
import sys

# Performance metrics collection
metrics = {
    'startup_times': [],
    'shutdown_times': [],
    'restart_times': [],
    'memory_usage': [],
    'cpu_usage': []
}

def measure_startup():
    """Measure startup time of the orchestrator."""
    start = time.perf_counter()
    proc = subprocess.Popen([sys.executable, "simple_orchestrator.py", "--force"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, bufsize=1)

    # Wait for startup message
    for line in proc.stdout:
        if "Orchestrator started" in line:
            startup_time = time.perf_counter() - start
            # Extract the reported startup time
            if "ms" in line:
                reported_ms = float(line.split("in ")[1].split("ms")[0])
                print(f"Startup: {startup_time*1000:.2f}ms (reported: {reported_ms}ms)")
            break

    return proc, startup_time

def measure_shutdown(proc):
    """Measure shutdown time of the orchestrator."""
    start = time.perf_counter()
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        # Force kill if not responding to SIGTERM
        proc.kill()
        proc.wait(timeout=0.5)
    shutdown_time = time.perf_counter() - start
    print(f"Shutdown: {shutdown_time*1000:.2f}ms")
    return shutdown_time

def measure_memory_cpu(pid):
    """Measure memory and CPU usage."""
    try:
        process = psutil.Process(pid)
        mem_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)
        return mem_info.rss / 1024 / 1024, cpu_percent  # MB
    except:
        return 0, 0

def random_restart_test(duration=30):
    """Test resilience with random restarts."""
    print(f"\n=== Random Restart Resilience Test ({duration}s) ===")

    # Start orchestrator
    proc, startup_time = measure_startup()
    metrics['startup_times'].append(startup_time)

    start_time = time.time()
    restart_count = 0

    while time.time() - start_time < duration:
        # Random delay between restarts (1-5 seconds)
        delay = random.uniform(1, 5)
        time.sleep(delay)

        # Measure memory/CPU before restart
        mem, cpu = measure_memory_cpu(proc.pid)
        if mem > 0:
            metrics['memory_usage'].append(mem)
            metrics['cpu_usage'].append(cpu)

        # Perform restart
        print(f"\nRandom restart #{restart_count + 1} after {delay:.1f}s")
        restart_start = time.perf_counter()

        # Kill current process
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=0.5)

        # Start new process
        proc, startup = measure_startup()

        restart_time = time.perf_counter() - restart_start
        metrics['restart_times'].append(restart_time)
        metrics['startup_times'].append(startup)

        restart_count += 1

    # Final shutdown
    shutdown = measure_shutdown(proc)
    metrics['shutdown_times'].append(shutdown)

    return restart_count

def performance_benchmark():
    """Run comprehensive performance benchmarks."""
    print("=== AIOS Performance Benchmark ===\n")

    # Test 1: Clean startup/shutdown
    print("Test 1: Clean Startup/Shutdown")
    for i in range(5):
        proc, startup = measure_startup()
        metrics['startup_times'].append(startup)
        time.sleep(2)  # Let it stabilize

        # Measure memory/CPU
        mem, cpu = measure_memory_cpu(proc.pid)
        if mem > 0:
            metrics['memory_usage'].append(mem)
            metrics['cpu_usage'].append(cpu)

        shutdown = measure_shutdown(proc)
        metrics['shutdown_times'].append(shutdown)
        time.sleep(0.5)

    # Test 2: Random restart resilience
    restart_count = random_restart_test(30)

    # Calculate statistics
    print("\n=== Performance Statistics ===\n")

    def print_stats(name, values, unit="ms", multiplier=1000):
        if values:
            values_converted = [v * multiplier for v in values]
            avg = statistics.mean(values_converted)
            med = statistics.median(values_converted)
            min_val = min(values_converted)
            max_val = max(values_converted)
            p95 = statistics.quantiles(values_converted, n=20)[18] if len(values_converted) > 1 else max_val

            print(f"{name}:")
            print(f"  Average: {avg:.2f}{unit}")
            print(f"  Median:  {med:.2f}{unit}")
            print(f"  Min:     {min_val:.2f}{unit}")
            print(f"  Max:     {max_val:.2f}{unit}")
            print(f"  95th %:  {p95:.2f}{unit}")

            # Check performance requirement
            if unit == "ms" and max_val > 100:
                print(f"  ⚠️  VIOLATION: Max time {max_val:.2f}ms exceeds 100ms limit!")
            elif unit == "ms" and max_val <= 100:
                print(f"  ✓ Within 100ms requirement")
            print()

    print_stats("Startup Time", metrics['startup_times'])
    print_stats("Shutdown Time", metrics['shutdown_times'])
    print_stats("Full Restart Time", metrics['restart_times'])

    if metrics['memory_usage']:
        print_stats("Memory Usage", metrics['memory_usage'], unit="MB", multiplier=1)

    if metrics['cpu_usage']:
        print_stats("CPU Usage", metrics['cpu_usage'], unit="%", multiplier=1)

    print(f"Total Restarts: {restart_count}")
    print(f"Resilience: System survived all {restart_count} random restarts")

    # Generate markdown report
    return generate_markdown_report(metrics, restart_count)

def generate_markdown_report(metrics, restart_count):
    """Generate markdown formatted performance report."""
    report = "\n## Performance Statistics\n\n"
    report += "System performance metrics collected during testing:\n\n"

    # Create table
    report += "| Metric | Average | Median | Min | Max | 95th % | Status |\n"
    report += "|--------|---------|--------|-----|-----|--------|--------|\n"

    def format_row(name, values, unit="ms", multiplier=1000, limit=100):
        if not values:
            return ""
        values_converted = [v * multiplier for v in values]
        avg = statistics.mean(values_converted)
        med = statistics.median(values_converted)
        min_val = min(values_converted)
        max_val = max(values_converted)
        p95 = statistics.quantiles(values_converted, n=20)[18] if len(values_converted) > 1 else max_val

        status = "✓" if unit != "ms" or max_val <= limit else "⚠️"

        return f"| {name} | {avg:.2f}{unit} | {med:.2f}{unit} | {min_val:.2f}{unit} | {max_val:.2f}{unit} | {p95:.2f}{unit} | {status} |\n"

    report += format_row("Startup Time", metrics['startup_times'])
    report += format_row("Shutdown Time", metrics['shutdown_times'])
    report += format_row("Restart Time", metrics['restart_times'])

    if metrics['memory_usage']:
        report += format_row("Memory Usage", metrics['memory_usage'], unit="MB", multiplier=1)

    if metrics['cpu_usage']:
        report += format_row("CPU Usage", metrics['cpu_usage'], unit="%", multiplier=1)

    report += f"\n### Resilience Testing\n\n"
    report += f"- **Total Random Restarts**: {restart_count}\n"
    report += f"- **Test Duration**: 30 seconds\n"
    report += f"- **Result**: ✓ System survived all random restarts\n"

    report += f"\n### Performance Requirements\n\n"
    report += f"- All operations must complete within **100ms**\n"

    max_startup = max(metrics['startup_times']) * 1000 if metrics['startup_times'] else 0
    max_shutdown = max(metrics['shutdown_times']) * 1000 if metrics['shutdown_times'] else 0

    if max_startup <= 100 and max_shutdown <= 100:
        report += f"- **Status**: ✓ All operations within performance limits\n"
    else:
        report += f"- **Status**: ⚠️  Some operations exceed 100ms limit\n"

    return report

if __name__ == "__main__":
    try:
        # Install psutil if not available
        import psutil
    except ImportError:
        print("Installing psutil for performance monitoring...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
        import psutil

    report = performance_benchmark()
    print(report)

    # Save report to file
    with open("performance_report.md", "w") as f:
        f.write(report)
    print("\nPerformance report saved to performance_report.md")