#!/usr/bin/env python3
"""
Comprehensive benchmark: Web UI candidates × Shell configs × Commands
Tests: aio, ls across different subprocess invocation methods
"""
import subprocess, time, sys, os, signal

# Candidates that support arbitrary commands
CANDIDATES = [
    {"file": "10_fastapi_query.py", "port": 8000, "url": "http://127.0.0.1:8000/?c={cmd}", "name": "fastapi-query"},
    {"file": "12_flask_form.py", "port": 5000, "url": "http://127.0.0.1:5000/", "post": True, "name": "flask-form"},
    {"file": "13_flask_template.py", "port": 5000, "url": "http://127.0.0.1:5000/?cmd={cmd}", "name": "flask-template"},
]

# Shell invocation methods to test
SHELL_METHODS = [
    ("direct", lambda cmd: cmd),
    ("source", lambda cmd: f"source ~/.bashrc 2>/dev/null && {cmd}"),
    ("bash -i", lambda cmd: f"bash -i -c {repr(cmd)}"),
]

COMMANDS = ["ls", "aio"]

def wait_server(port, timeout=8):
    """Wait for server to be ready."""
    import requests
    for _ in range(int(timeout * 10)):
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=0.5)
            return True
        except: time.sleep(0.1)
    return False

def bench_subprocess(cmd, runs=5):
    """Benchmark subprocess.getoutput directly (no web server)."""
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        subprocess.getoutput(cmd)
        times.append(time.perf_counter() - t)
    return min(times) * 1000  # Return best time in ms

def bench_candidate(candidate, cmd, shell_method, runs=3):
    """Benchmark a web UI candidate with given shell method."""
    import requests

    # Modify candidate to use shell method
    shell_cmd = shell_method(cmd)

    # Start server with modified subprocess call
    # We can't easily modify the candidates, so we test the subprocess methods directly
    # and multiply by the HTTP overhead measured separately
    return None  # Candidates use hardcoded subprocess, can't inject shell method

def run_benchmarks():
    """Run all benchmarks and collect results."""
    results = []

    print("=" * 70)
    print("SUBPROCESS SHELL METHOD BENCHMARKS")
    print("=" * 70)
    print(f"\n{'Method':<12} {'Command':<8} {'Time (ms)':>10}")
    print("-" * 35)

    # Test each shell method with each command
    for method_name, method_fn in SHELL_METHODS:
        for cmd in COMMANDS:
            shell_cmd = method_fn(cmd)
            t = bench_subprocess(shell_cmd)
            results.append({
                "context": "subprocess",
                "method": method_name,
                "command": cmd,
                "time_ms": t
            })
            print(f"{method_name:<12} {cmd:<8} {t:>10.2f}")

    # Test in tmux context
    print("\n" + "=" * 70)
    print("TMUX CONTEXT BENCHMARKS")
    print("=" * 70)
    print(f"\n{'Method':<12} {'Command':<8} {'Time (ms)':>10}")
    print("-" * 35)

    for method_name, method_fn in SHELL_METHODS:
        for cmd in COMMANDS:
            shell_cmd = method_fn(cmd)
            # Run benchmark inside tmux
            tmux_cmd = f"for i in 1 2 3 4 5; do {shell_cmd} >/dev/null; done"

            t = time.perf_counter()
            subprocess.run(
                ["tmux", "new-window", "-d", "-n", "bench", f"bash -c '{tmux_cmd}; sleep 0.1'"],
                capture_output=True
            )
            time.sleep(0.8)  # Wait for commands to complete
            subprocess.run(["tmux", "kill-window", "-t", "bench"], capture_output=True)
            elapsed = (time.perf_counter() - t - 0.8) / 5 * 1000  # Rough per-command estimate

            # More accurate: run single command with time
            result = subprocess.run(
                ["tmux", "new-window", "-d", "-n", "bench2",
                 f"bash -c 'echo $(($(date +%s%N)/1000000)) > /tmp/t1; {shell_cmd} >/dev/null; echo $(($(date +%s%N)/1000000)) > /tmp/t2'"],
                capture_output=True
            )
            time.sleep(0.5)
            try:
                t1 = int(open("/tmp/t1").read().strip())
                t2 = int(open("/tmp/t2").read().strip())
                elapsed = t2 - t1
            except:
                elapsed = 0
            subprocess.run(["tmux", "kill-window", "-t", "bench2"], capture_output=True)

            results.append({
                "context": "tmux",
                "method": method_name,
                "command": cmd,
                "time_ms": elapsed
            })
            print(f"{method_name:<12} {cmd:<8} {elapsed:>10.2f}")

    # Test web UI candidates
    print("\n" + "=" * 70)
    print("WEB UI CANDIDATE BENCHMARKS (native subprocess.getoutput)")
    print("=" * 70)

    import requests

    for c in CANDIDATES:
        filepath = os.path.join(os.path.dirname(__file__), "candidates", c["file"])
        if not os.path.exists(filepath):
            print(f"\nSkipping {c['name']} - file not found")
            continue

        print(f"\n{c['name']}:")
        print(f"  {'Command':<8} {'Time (ms)':>10}")
        print(f"  {'-' * 20}")

        # Start server
        proc = subprocess.Popen(
            [sys.executable, filepath],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )

        try:
            if not wait_server(c["port"]):
                print(f"  Server failed to start")
                continue
            time.sleep(0.3)

            for cmd in COMMANDS:
                times = []
                for _ in range(5):
                    t = time.perf_counter()
                    try:
                        if c.get("post"):
                            requests.post(c["url"], data={"cmd": cmd}, timeout=5)
                        else:
                            requests.get(c["url"].format(cmd=cmd), timeout=5)
                        times.append(time.perf_counter() - t)
                    except Exception as e:
                        times.append(None)

                valid = [x for x in times if x]
                avg = min(valid) * 1000 if valid else 0
                results.append({
                    "context": c["name"],
                    "method": "native",
                    "command": cmd,
                    "time_ms": avg
                })
                print(f"  {cmd:<8} {avg:>10.2f}")
        finally:
            try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except: proc.terminate()
            proc.wait()
            time.sleep(0.3)

    return results

def print_summary_table(results):
    """Print markdown summary table."""
    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)

    # Group by command
    for cmd in COMMANDS:
        print(f"\n## {cmd.upper()} Command Performance\n")
        print("| Context | Method | Time (ms) | vs Direct |")
        print("|---------|--------|-----------|-----------|")

        cmd_results = [r for r in results if r["command"] == cmd]

        # Find direct subprocess as baseline
        baseline = next((r["time_ms"] for r in cmd_results
                        if r["context"] == "subprocess" and r["method"] == "direct"), 1)

        for r in cmd_results:
            speedup = baseline / r["time_ms"] if r["time_ms"] > 0 else 0
            speedup_str = f"{speedup:.1f}x" if speedup != 1 else "-"
            print(f"| {r['context']:<12} | {r['method']:<8} | {r['time_ms']:>9.2f} | {speedup_str:>9} |")

if __name__ == "__main__":
    results = run_benchmarks()
    print_summary_table(results)
