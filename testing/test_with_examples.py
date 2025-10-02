#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

sys.path.append('/home/seanpatten/projects/AIOS')

examples = [
    {
        "name": "Todo Manager",
        "commands": [
            ("python3 programs/todo/todo.py list", "Shows list of tasks with numbers"),
            ("python3 programs/todo/todo.py add 'Example task'", "Adds a new task"),
            ("python3 programs/todo/todo.py done 1", "Marks task 1 as done"),
            ("python3 programs/todo/todo.py clear", "Removes completed tasks")
        ]
    },
    {
        "name": "Services",
        "commands": [
            ("python3 services/service.py list", "Lists all services and status"),
            ("python3 services/service.py start myapp", "Starts service 'myapp'"),
            ("python3 services/service.py stop myapp", "Stops service 'myapp'"),
            ("python3 services/service.py status myapp", "Shows status of 'myapp'")
        ]
    },
    {
        "name": "Feed/Messages",
        "commands": [
            ("python3 services/feed.py list", "Lists recent messages"),
            ("python3 services/feed.py add 'System update complete'", "Adds a message"),
            ("python3 services/feed.py clear", "Clears old messages (>7 days)")
        ]
    },
    {
        "name": "Jobs",
        "commands": [
            ("python3 services/jobs.py summary", "Shows job summary"),
            ("python3 services/jobs.py list", "Lists all jobs with status"),
            ("python3 services/jobs.py running", "Shows running jobs (HTML)"),
            ("python3 services/jobs.py accept 1", "Accepts job with ID 1")
        ]
    },
    {
        "name": "Processes",
        "commands": [
            ("python3 services/processes.py json", "Outputs process info as JSON"),
            ("python3 services/processes.py list", "Lists scheduled/ongoing/core processes")
        ]
    },
    {
        "name": "AIOS Control",
        "commands": [
            ("python3 aios_start.py status", "Shows AIOS PIDs"),
            ("python3 aios_start.py start", "Starts AIOS web interface"),
            ("python3 aios_start.py stop", "Stops AIOS")
        ]
    }
]

def test_example(example):
    print(f"\n{'='*70}")
    print(f" {example['name']}")
    print('='*70)

    for cmd, description in example['commands']:
        print(f"\nCommand: {cmd}")
        print(f"Purpose: {description}")
        print('-'*50)

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2)
        output = result.stdout or result.stderr or "(no output)"

        lines = output.strip().split('\n')[:5]
        for line in lines:
            print(f"  {line[:80]}")

        if len(output.strip().split('\n')) > 5:
            print("  ...")

        status = "✓" if result.returncode == 0 else "✗"
        print(f"Status: {status}")

def main():
    print("=" * 70)
    print(" ⚠️  MANUAL VERIFICATION REQUIRED")
    print("=" * 70)
    print(" This test shows command outputs but DOES NOT verify correctness.")
    print(" A human or LLM must manually review each output to confirm:")
    print("   - Output matches expected format")
    print("   - Data values are reasonable")
    print("   - Commands behave as documented")
    print("=" * 70)
    print()
    print(" AIOS Testing Guide - Sample Commands and Expected Output")
    print("=" * 70)
    print("\nThis shows what each command does and sample output.")
    print("Verify outputs match expected behavior.\n")

    for example in examples:
        test_example(example)

    print(f"\n{'='*70}")
    print(" Testing Complete - Review outputs above for correctness")
    print('='*70)
    print("\n⚠️  IMPORTANT: Status ✓ only means no errors - verify output is correct!")

if __name__ == "__main__":
    main()