#!/usr/bin/env python3
"""Generate candidates.txt with filenames and complete source code"""

from pathlib import Path

# All candidate files
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

# Generate the combined file
with open("candidates.txt", "w") as output:
    for i, candidate in enumerate(candidates):
        if Path(candidate).exists():
            print(f"✓ Adding {candidate}")

            # Write filename
            output.write(f"{candidate}\n")
            output.write("=" * 80 + "\n")

            # Write complete source code
            with open(candidate, "r") as source:
                output.write(source.read())

            # Add separator between files (except for last one)
            if i < len(candidates) - 1:
                output.write("\n\n")
                output.write("#" * 80 + "\n")
                output.write("#" * 80 + "\n\n")
        else:
            print(f"✗ Missing: {candidate}")

print(f"\n✅ Created candidates.txt with {len(candidates)} complete implementations")
print(f"File size: {Path('candidates.txt').stat().st_size:,} bytes")