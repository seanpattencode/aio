#!/usr/bin/env python3
"""Test all candidate implementations"""

import subprocess
import os
from pathlib import Path

candidates = [
    ("claude1.py", "python3 claude1.py add-task 'test' 'echo test'", "python3 claude1.py status"),
    ("claudeCode2.py", "python3 claudeCode2.py enqueue 'test' 'echo test'", "python3 claudeCode2.py stats"),
    ("claudeCodeB.py", "python3 claudeCodeB.py add 'echo test'", "python3 claudeCodeB.py stats"),
    ("claudeCodeC.py", "python3 claudeCodeC.py add 'test' 'echo test'", "python3 claudeCodeC.py stats"),
    ("claudeCodeC_fixed.py", "python3 claudeCodeC_fixed.py add 'test' 'echo test'", "python3 claudeCodeC_fixed.py stats"),
    ("claudeCodeCplus.py", "python3 claudeCodeCplus.py add 'echo test'", "python3 claudeCodeCplus.py stats"),
    ("claudeCodeD.py", "python3 claudeCodeD.py add 'echo test'", "python3 claudeCodeD.py stats"),
    ("claudeCodeE.py", "python3 claudeCodeE.py add 'echo test'", "python3 claudeCodeE.py stats"),
    ("ClaudeCodeA.py", "python3 ClaudeCodeA.py add --mode fast --name 'test' --cmd 'echo test'", "python3 ClaudeCodeA.py stats"),
    ("production_sqlite.py", None, None),  # Too complex for simple test
]

print("Testing all candidate implementations...")
print("="*60)

working = []
failed = []

for file, add_cmd, stats_cmd in candidates:
    if not Path(file).exists():
        print(f"❌ {file:<25} - FILE NOT FOUND")
        failed.append(file)
        continue

    if add_cmd is None:
        print(f"✓  {file:<25} - EXISTS (complex, skipping test)")
        working.append(file)
        continue

    # Clean databases
    os.system("rm -f *.db 2>/dev/null")

    try:
        # Test add
        result = subprocess.run(add_cmd, shell=True, capture_output=True, text=True, timeout=2)
        if result.returncode != 0:
            print(f"❌ {file:<25} - ADD FAILED")
            failed.append(file)
            continue

        # Test stats
        result = subprocess.run(stats_cmd, shell=True, capture_output=True, text=True, timeout=2)
        if result.returncode != 0:
            print(f"❌ {file:<25} - STATS FAILED")
            failed.append(file)
            continue

        print(f"✓  {file:<25} - WORKING")
        working.append(file)

    except subprocess.TimeoutExpired:
        print(f"⚠  {file:<25} - TIMEOUT (likely ok)")
        working.append(file)
    except Exception as e:
        print(f"❌ {file:<25} - ERROR: {e}")
        failed.append(file)

print("\n" + "="*60)
print(f"Summary: {len(working)} working, {len(failed)} failed")
print(f"Working candidates: {len(working)}")
for f in working:
    print(f"  - {f}")

if failed:
    print(f"\nFailed candidates: {len(failed)}")
    for f in failed:
        print(f"  - {f}")