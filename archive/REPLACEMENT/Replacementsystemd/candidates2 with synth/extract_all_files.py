#!/usr/bin/env python3
"""
Extract all files in current directory to a single text file
"""
import os
from pathlib import Path

def extract_files():
    current_dir = Path(".")
    output_file = "all_candidates_source.txt"

    # Get all Python and C++ files
    files = sorted(list(current_dir.glob("*.py")) + list(current_dir.glob("*.cpp")))

    # Exclude this script
    files = [f for f in files if f.name != "extract_all_files.py" and f.name != output_file]

    with open(output_file, "w") as out:
        out.write("=" * 80 + "\n")
        out.write("SYSTEMD CANDIDATES1 - ALL SOURCE FILES\n")
        out.write("=" * 80 + "\n\n")

        for file_path in files:
            print(f"Processing: {file_path.name}")

            # Write file header
            out.write("=" * 80 + "\n")
            out.write(f"FILE: {file_path.name}\n")
            out.write("=" * 80 + "\n\n")

            try:
                # Read and write file content
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    out.write(content)
                    if not content.endswith("\n"):
                        out.write("\n")
                    out.write("\n\n")
            except Exception as e:
                out.write(f"ERROR READING FILE: {e}\n\n")

    print(f"\nExtracted {len(files)} files to {output_file}")

    # Show summary
    total_size = sum(f.stat().st_size for f in files)
    print(f"Total size: {total_size:,} bytes")
    print("\nFiles included:")
    for f in files:
        print(f"  - {f.name} ({f.stat().st_size:,} bytes)")

if __name__ == "__main__":
    extract_files()