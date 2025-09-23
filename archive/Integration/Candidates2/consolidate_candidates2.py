#!/usr/bin/env python3
"""
Script to consolidate all files from current directory (Candidates2)
into a single text file with filename headers and code content.
Excludes itself from the consolidation.
"""

import os
from pathlib import Path

def consolidate_files():
    # Use current directory
    source_dir = Path(".")
    output_file = "candidates2_consolidated.txt"
    script_name = "consolidate_candidates2.py"

    # Get all Python files in the directory, excluding this script
    py_files = sorted([f for f in source_dir.glob("*.py")
                      if f.name != script_name])

    if not py_files:
        print(f"No Python files found to consolidate")
        return

    # Create consolidated output
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write(f"CONSOLIDATED FILES FROM {source_dir.resolve()}\n")
        outfile.write("=" * 80 + "\n\n")

        for i, filepath in enumerate(py_files, 1):
            print(f"Processing {i}/{len(py_files)}: {filepath.name}")

            # Write file header
            outfile.write(f"\n{'='*80}\n")
            outfile.write(f"FILE: {filepath.name}\n")
            outfile.write(f"{'='*80}\n\n")

            # Write file content
            try:
                with open(filepath, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    outfile.write(content)
                    if not content.endswith('\n'):
                        outfile.write('\n')
            except Exception as e:
                outfile.write(f"ERROR READING FILE: {e}\n")

            outfile.write(f"\n{'='*80}\n")

    # Get file size
    file_size = os.path.getsize(output_file)
    file_size_kb = file_size / 1024

    print(f"\n✅ Successfully consolidated {len(py_files)} files")
    print(f"📄 Output file: {output_file}")
    print(f"📊 Total size: {file_size_kb:.2f} KB ({file_size:,} bytes)")
    print(f"📁 Files included:")
    for f in py_files:
        print(f"   - {f.name}")

if __name__ == "__main__":
    consolidate_files()