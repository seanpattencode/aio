#!/usr/bin/env python3
"""Consolidate all Python solutions in this folder into one text file"""

import os
from pathlib import Path

def consolidate_solutions():
    current_dir = Path(__file__).parent
    output_file = current_dir / "consolidated_solutions.txt"

    # Get all Python files except this script
    py_files = [f for f in current_dir.glob("*.py")
                if f.name != "consolidate.py" and f.is_file()]

    # Sort files alphabetically
    py_files.sort(key=lambda x: x.name)

    with open(output_file, 'w') as out:
        out.write("=" * 80 + "\n")
        out.write("CONSOLIDATED PYTHON SOLUTIONS\n")
        out.write("=" * 80 + "\n\n")

        # Write table of contents
        out.write("TABLE OF CONTENTS:\n")
        out.write("-" * 40 + "\n")
        for i, file in enumerate(py_files, 1):
            out.write(f"{i}. {file.name}\n")
        out.write("\n" + "=" * 80 + "\n\n")

        # Write each file's content
        for file in py_files:
            out.write("=" * 80 + "\n")
            out.write(f"FILE: {file.name}\n")
            out.write("=" * 80 + "\n\n")

            try:
                with open(file, 'r') as f:
                    content = f.read()
                    out.write(content)
                    if not content.endswith('\n'):
                        out.write('\n')
            except Exception as e:
                out.write(f"ERROR reading file: {e}\n")

            out.write("\n" + "=" * 80 + "\n\n")

        # Write summary
        out.write("SUMMARY:\n")
        out.write("-" * 40 + "\n")
        out.write(f"Total files consolidated: {len(py_files)}\n")
        out.write(f"Files included:\n")
        for file in py_files:
            # Get file size and line count
            size = file.stat().st_size
            with open(file, 'r') as f:
                lines = len(f.readlines())
            out.write(f"  - {file.name}: {lines} lines, {size:,} bytes\n")

    print(f"Consolidated {len(py_files)} Python files into {output_file.name}")
    print(f"Files included: {', '.join(f.name for f in py_files)}")
    print(f"Output file: {output_file.absolute()}")

if __name__ == "__main__":
    consolidate_solutions()