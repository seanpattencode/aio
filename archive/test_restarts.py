#!/usr/bin/env python3
"""Test script to verify orchestrator resilience to random restarts."""

import subprocess
import time
import random
import signal
import sys

def run_test():
    print("Testing orchestrator resilience to random restarts...")
    print("Starting orchestrator...")

    # Start the orchestrator
    proc = subprocess.Popen(
        ["python3", "simple_orchestrator.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    start_time = time.time()
    test_duration = 30  # Run test for 30 seconds
    restart_count = 0

    try:
        while time.time() - start_time < test_duration:
            # Random wait between 2-5 seconds
            wait_time = random.uniform(2, 5)
            print(f"Running for {wait_time:.1f} seconds...")

            # Collect output for this period
            deadline = time.time() + wait_time
            while time.time() < deadline:
                try:
                    line = proc.stdout.readline()
                    if line:
                        print(f"  {line.strip()}")
                except:
                    break
                time.sleep(0.1)

            # Send SIGTERM to simulate restart
            print(f"Sending SIGTERM (restart #{restart_count + 1})...")
            proc.send_signal(signal.SIGTERM)

            # Wait for process to die
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                print("Process didn't die gracefully, killing...")
                proc.kill()
                proc.wait()

            restart_count += 1

            # Restart the orchestrator
            print("Restarting orchestrator...")
            proc = subprocess.Popen(
                ["python3", "simple_orchestrator.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

        print(f"\nTest completed!")
        print(f"Total restarts: {restart_count}")
        print(f"Average uptime: {test_duration/restart_count:.1f} seconds")

    finally:
        # Clean up
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except:
            proc.kill()

if __name__ == "__main__":
    run_test()