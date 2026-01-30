#!/usr/bin/env python3
"""
Run all generated scripts and collect results.
"""

import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

COMMANDS_DIR = Path(__file__).parent / "generated_commands"
RESULTS_DIR = Path(__file__).parent / "results"
MAX_PARALLEL = 20
TIMEOUT = 10  # 10 sec max per script

def extract_python(txt_file):
    """Extract Python code from txt file."""
    content = txt_file.read_text()

    # Try to find code between ```python and ```
    if "```python" in content:
        start = content.find("```python") + 9
        end = content.find("```", start)
        if end > start:
            return content[start:end].strip()

    # Try ``` without python specifier
    if "```" in content:
        parts = content.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1 and "import" in part:  # Odd parts are code blocks
                # Remove language specifier if present
                lines = part.strip().split('\n')
                if lines and lines[0] in ['python', 'py', '']:
                    lines = lines[1:]
                return '\n'.join(lines).strip()

    # Skip header comments and return rest
    lines = content.split('\n')
    code_lines = []
    in_code = False
    for line in lines:
        if line.startswith('# Dataset:') or line.startswith('# Size:'):
            continue
        if 'import' in line or 'from ' in line:
            in_code = True
        if in_code:
            code_lines.append(line)

    if code_lines:
        return '\n'.join(code_lines).strip()

    return content

def run_script(txt_file):
    """Run a single script and return results."""
    name = txt_file.stem
    print(f"[RUN] {name}", flush=True)

    code = extract_python(txt_file)

    try:
        result = subprocess.run(
            ["uv", "run", "--with", "datasets", "--with", "scikit-learn", "--with", "pandas", "--with", "numpy", "python", "-c", code],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

        output = result.stdout + result.stderr
        status = "OK" if result.returncode == 0 else "FAIL"

        # Save result
        out_file = RESULTS_DIR / f"{name}_result.txt"
        with open(out_file, 'w') as f:
            f.write(f"# {name}\n# Status: {status}\n\n")
            f.write(output)

        # Extract accuracy if present
        acc = "N/A"
        for line in output.split("\n"):
            if "accuracy" in line.lower():
                acc = line.strip()
                break

        print(f"[{status}] {name}: {acc}", flush=True)
        return (name, status, acc)

    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {name}", flush=True)
        return (name, "TIMEOUT", "N/A")
    except Exception as e:
        print(f"[ERROR] {name}: {e}", flush=True)
        return (name, "ERROR", str(e))

def main():
    RESULTS_DIR.mkdir(exist_ok=True)

    scripts = sorted(COMMANDS_DIR.glob("*.txt"))
    if not scripts:
        print("No scripts found in generated_commands/")
        return

    print(f"\n{'='*60}")
    print(f" RUNNING {len(scripts)} SCRIPTS")
    print(f"{'='*60}\n")

    results = []

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        futures = {executor.submit(run_script, s): s for s in scripts}
        for future in as_completed(futures):
            results.append(future.result())

    # Summary
    print(f"\n{'='*60}")
    print(" RESULTS SUMMARY")
    print(f"{'='*60}")

    ok = sum(1 for r in results if r[1] == "OK")
    print(f"\nSuccess: {ok}/{len(results)}\n")

    print(f"{'Dataset':<40} {'Status':<10} {'Result'}")
    print("-" * 70)
    for name, status, acc in sorted(results):
        print(f"{name:<40} {status:<10} {acc}")

    # Save summary
    with open(RESULTS_DIR / "SUMMARY.txt", 'w') as f:
        f.write(f"Success: {ok}/{len(results)}\n\n")
        for name, status, acc in sorted(results):
            f.write(f"{name}: {status} - {acc}\n")

    print(f"\nResults saved to: {RESULTS_DIR}")

if __name__ == "__main__":
    main()
