#!/usr/bin/env python3
"""
Agent Spawner - Spawns Claude CLI to work on CFA dataset experiments.

Usage:
  python agent_spawner.py              # Interactive mode
  python agent_spawner.py --list       # List available datasets
  python agent_spawner.py --all        # Run all datasets one by one
  python agent_spawner.py ChemBench    # Run specific dataset
"""

import subprocess
import sys
import signal
import os
import csv
import json
import threading
from pathlib import Path

# Datasets already completed - skip these
COMPLETED_DATASETS = {
    "disco-eth/AgentsNet",
}

PROMPT_FILE = Path(__file__).parent / "CONTINUE_PROMPT.md"
DATASETS_FILE = Path(__file__).parent.parent.parent / "aWorktrees/quantumfusion-20260130-032056/step_1/small_datasets.csv"

def load_datasets():
    """Load datasets from small_datasets.csv."""
    datasets = []

    # Try multiple possible locations
    possible_paths = [
        DATASETS_FILE,
        Path(__file__).parent / "small_datasets.csv",
        Path.home() / "projects/aWorktrees/quantumfusion-20260130-032056/step_1/small_datasets.csv",
        Path.home() / "projects/aWorktrees/quantumfusion-20260130-032056/data_shared/small_datasets.csv",
    ]

    csv_path = None
    for p in possible_paths:
        if p.exists():
            csv_path = p
            break

    if not csv_path:
        print(f"[ERROR] Could not find small_datasets.csv")
        print(f"Tried: {possible_paths}")
        return []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('name', '')
            size = row.get('size_mb', '0')
            if name and name not in COMPLETED_DATASETS:
                datasets.append((name, f"{size}MB"))

    return datasets


def load_base_prompt():
    """Load the continuation prompt."""
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text()
    return ""


def build_prompt(dataset_name, dataset_desc):
    """Build a short prompt that references the file."""
    return f"""Read step_1/CONTINUE_PROMPT.md first, then run a CFA experiment on dataset: {dataset_name} ({dataset_desc}). Keep it minimal and debug as you go."""


def list_datasets():
    """Print available datasets."""
    datasets = load_datasets()
    print(f"\n Available Datasets: {len(datasets)} total")
    print("-" * 60)
    for i, (name, size) in enumerate(datasets[:50], 1):  # Show first 50
        print(f"  {i:3}. {name:<45} {size}")
    if len(datasets) > 50:
        print(f"\n  ... and {len(datasets) - 50} more")
    print("-" * 60)


TIMEOUT_SECONDS = 600  # 10 minutes

def spawn_agent(dataset_name, dataset_desc, show_output=True):
    """Spawn Claude CLI with the prompt."""
    prompt = build_prompt(dataset_name, dataset_desc)

    print("=" * 60)
    print(" SPAWNING AGENT")
    print("=" * 60)
    print(f"Dataset: {dataset_name}")
    print(f"Size: {dataset_desc}")
    print(f"Timeout: {TIMEOUT_SECONDS}s ({TIMEOUT_SECONDS//60} min)")
    print(f"Working dir: {Path.cwd()}")
    print("-" * 60)
    print("Press Ctrl+C to stop the agent")
    print("=" * 60)
    print()
    sys.stdout.flush()

    # Spawn claude CLI with streaming JSON output
    proc = subprocess.Popen(
        ["claude", "-p", "--verbose", "--output-format", "stream-json", prompt],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    # Parse and display streaming output
    def stream_output(pipe, is_stderr=False):
        for line in pipe:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                msg_type = data.get("type", "")

                if msg_type == "assistant":
                    content = data.get("message", {}).get("content", [])
                    for block in content:
                        if block.get("type") == "text":
                            print(block.get("text", ""), end="", flush=True)
                        elif block.get("type") == "tool_use":
                            tool = block.get("name", "tool")
                            inp = str(block.get("input", {}))[:100]
                            print(f"\n[TOOL: {tool}] {inp}...", flush=True)
                elif msg_type == "result":
                    cost = data.get("cost_usd", 0)
                    print(f"\n[COST: ${cost:.4f}]", flush=True)
            except json.JSONDecodeError:
                if is_stderr:
                    print(f"[ERR] {line}", flush=True)
                else:
                    print(line, flush=True)

    stdout_thread = threading.Thread(target=stream_output, args=(proc.stdout, False))
    stderr_thread = threading.Thread(target=stream_output, args=(proc.stderr, True))
    stdout_thread.start()
    stderr_thread.start()

    def signal_handler(sig, frame):
        print("\n\n[STOPPING AGENT...]")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[AGENT STOPPED]")
        raise KeyboardInterrupt()

    old_handler = signal.signal(signal.SIGINT, signal_handler)

    try:
        # Wait with timeout
        return_code = proc.wait(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        print(f"\n[TIMEOUT] {TIMEOUT_SECONDS}s exceeded, killing agent...")
        proc.kill()
        proc.wait()
        return_code = -1
    finally:
        signal.signal(signal.SIGINT, old_handler)
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

    print("\n" + "=" * 60)
    print(f"[AGENT FINISHED] Exit code: {return_code}")
    print("=" * 60)
    sys.stdout.flush()

    return return_code


def run_all():
    """Run agent on all datasets sequentially."""
    datasets = load_datasets()

    print("\n" + "=" * 60)
    print(f" RUNNING ALL DATASETS ({len(datasets)} total)")
    print("=" * 60)

    total = len(datasets)
    for i, (name, desc) in enumerate(datasets, 1):
        print(f"\n{'#' * 60}")
        print(f"# [{i}/{total}] Starting: {name}")
        print(f"{'#' * 60}")

        try:
            return_code = spawn_agent(name, desc, show_output=True)
            if return_code != 0:
                print(f"[WARNING] Agent exited with code {return_code}")
        except KeyboardInterrupt:
            print("\n[INTERRUPTED] Stop all runs? (y/n)")
            try:
                if input("> ").strip().lower() == 'y':
                    print("[STOPPING ALL]")
                    return
                else:
                    print("[CONTINUING TO NEXT DATASET]")
                    continue
            except (EOFError, KeyboardInterrupt):
                return

        print(f"\n[{i}/{total}] Completed: {name}")

    print("\n" + "=" * 60)
    print(" ALL DATASETS COMPLETED")
    print("=" * 60)


def main():
    print("\n" + "=" * 60)
    print(" CFA EXPERIMENT AGENT SPAWNER")
    print("=" * 60)

    datasets = load_datasets()
    print(f"Loaded {len(datasets)} datasets")

    # Check if dataset provided as argument
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            list_datasets()
            return

        if sys.argv[1] == "--all":
            run_all()
            return

        # Find matching dataset
        query = sys.argv[1].lower()
        for name, desc in datasets:
            if query in name.lower():
                spawn_agent(name, desc)
                return

        print(f"Dataset '{sys.argv[1]}' not found in list.")
        list_datasets()
        return

    # Interactive selection
    list_datasets()
    print("\nEnter dataset number, name, 'all', or 'q' to quit:")

    try:
        choice = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        return

    if choice.lower() == 'q':
        return

    if choice.lower() == 'all':
        run_all()
        return

    # Try as number
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(datasets):
            name, desc = datasets[idx]
            spawn_agent(name, desc)
            return
    except ValueError:
        pass

    # Try as name
    for name, desc in datasets:
        if choice.lower() in name.lower():
            spawn_agent(name, desc)
            return

    print(f"Invalid choice: {choice}")


if __name__ == "__main__":
    main()
