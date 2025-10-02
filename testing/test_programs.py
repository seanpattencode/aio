#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
from datetime import datetime

sys.path.append('/home/seanpatten/projects/AIOS')

test_configs = {
    "programs/todo/todo.py": ["list", "add 'Test task'", "list"],
    "services/service.py": ["list", "status"],
    "services/feed.py": ["list", "add 'Test message'", "view"],
    "services/scraper.py": [],
    "services/backup.py": [],
    "services/context_generator.py": [],
    "services/processes.py": ["json", "list"],
    "services/jobs.py": ["list", "summary"],
    "programs/ranker/ranker.py": ["list", "add 'Test idea'", "rank"],
    "programs/planner/planner.py": [],
    "programs/job_status.py": ["summary"],
    "programs/settings/settings.py": ["get theme", "set test_key test_value", "get test_key"],
    "programs/wiki_fetcher/wiki_fetcher.py": [],
    "programs/builder/builder.py": [],
    "programs/schedule/scheduler.py": [],
    "programs/autollm/autollm.py": ["status"],
    "programs/autollm/monitor.py": [],
    "programs/workflow/workflow.py": ["list"],
    "programs/worktree/worktree_manager.py": ["list"],
    "aios_start.py": ["status"],
    "core/aios_runner.py": ["echo 'test'"]
}

def run_test(script, commands):
    print(f"\n{'='*60}")
    print(f"Testing: {script}")
    print('='*60)

    results = []
    for cmd in commands:
        full_cmd = f"python3 {script} {cmd}"
        print(f"\n> {full_cmd}")
        print('-'*40)

        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=2)
        output = result.stdout or result.stderr or "(no output)"
        print(output[:500])
        results.append(result.returncode == 0)

    return all(results) if results else True

def main():
    root = Path('/home/seanpatten/projects/AIOS')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("="*70)
    print(" ⚠️  MANUAL VERIFICATION REQUIRED")
    print("="*70)
    print(" This test runs programs but DOES NOT verify output correctness.")
    print(" A human or LLM must manually inspect each output to confirm:")
    print("   - Output format is correct")
    print("   - Data is properly displayed")
    print("   - Commands produce expected results")
    print("="*70)
    print()

    print(f"AIOS Program Test Suite - {timestamp}")
    print("="*60)

    passed, failed, skipped = 0, 0, 0

    for script, commands in test_configs.items():
        script_path = root / script

        if not script_path.exists():
            print(f"\n⚠ SKIPPED: {script} (not found)")
            skipped += 1
            continue

        if not commands:
            print(f"\n⚠ SKIPPED: {script} (no test commands)")
            skipped += 1
            continue

        success = run_test(script_path, commands)
        if success:
            print(f"✓ PASSED")
            passed += 1
        else:
            print(f"✗ FAILED")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print('='*60)
    print("\n⚠️  REMEMBER: 'Passed' only means no errors occurred.")
    print("   Manual inspection of outputs above is required to confirm correctness!")

if __name__ == "__main__":
    main()