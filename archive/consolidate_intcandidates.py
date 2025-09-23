#!/usr/bin/env python3
"""
Script to consolidate all files from Integration/IntCandidates directory
into a single text file with filename headers and code content.
"""

import os
from pathlib import Path

def consolidate_files():
    # Define the directory path
    source_dir = Path("Integration/IntCandidates")
    output_file = "intcandidates_consolidated.txt"

    # Check if directory exists
    if not source_dir.exists():
        print(f"Error: Directory {source_dir} does not exist!")
        return

    # Get all Python files in the directory
    py_files = sorted(source_dir.glob("*.py"))

    if not py_files:
        print(f"No Python files found in {source_dir}")
        return

    # Create consolidated output
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write(f"CONSOLIDATED FILES FROM {source_dir}\n")
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