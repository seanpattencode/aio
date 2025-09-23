#!/usr/bin/env python3
"""Generate candidates.txt with all working implementations"""

from pathlib import Path

# All candidate files (excluding the broken original claudeCodeC.py)
candidates = [
    "claude1.py",
    "claudeCode2.py",
    "claudeCodeB.py",
    "claudeCodeC_fixed.py",
    "claudeCodeCplus.py",
    "claudeCodeD.py",
    "claudeCodeE.py",
    "ClaudeCodeA.py",
    "production_sqlite.py"
]

# Verify files exist and create the list
valid_candidates = []
for candidate in candidates:
    if Path(candidate).exists():
        valid_candidates.append(candidate)
        print(f"✓ Found: {candidate}")
    else:
        print(f"✗ Missing: {candidate}")

# Write to candidates.txt
with open("candidates.txt", "w") as f:
    for candidate in valid_candidates:
        f.write(f"{candidate}\n")

print(f"\n✅ Created candidates.txt with {len(valid_candidates)} implementations")
print("\nContents of candidates.txt:")
print("-" * 30)
with open("candidates.txt", "r") as f:
    print(f.read())