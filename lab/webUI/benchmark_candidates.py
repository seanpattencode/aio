#!/usr/bin/env python3
"""Benchmark all web UI candidates for ls and aio command execution times."""

import subprocess
import time
import requests
import signal
import os
import sys
import json

CANDIDATES = [
    {
        "file": "03_aiohttp_ws_timing.py",
        "port": 8080,
        "type": "http",
        "url_ls": "http://127.0.0.1:8080/",
        "url_aio": None,  # WebSocket based, can't easily test aio
        "method": "GET",
        "note": "WebSocket-based, testing page load only"
    },
    {
        "file": "06_flask_basic.py",
        "port": 5000,
        "type": "http",
        "url_ls": "http://127.0.0.1:5000/run",
        "url_aio": None,  # Only supports ls via button
        "method": "POST",
        "data": {"cmd": "ls"},
        "note": "POST form, hardcoded ls command"
    },
    {
        "file": "08_fastapi_basic.py",
        "port": 8000,
        "type": "http",
        "url_ls": "http://127.0.0.1:8000/",
        "url_aio": None,  # Hardcoded ls
        "method": "GET",
        "note": "Runs ls on page load"
    },
    {
        "file": "10_fastapi_query.py",
        "port": 8000,
        "type": "http",
        "url_ls": "http://127.0.0.1:8000/?c=ls",
        "url_aio": "http://127.0.0.1:8000/?c=aio",
        "method": "GET",
        "note": "Query param command"
    },
    {
        "file": "11_http_server_basic.py",
        "port": 8000,
        "type": "http",
        "url_ls": "http://127.0.0.1:8000/",
        "url_aio": None,  # Hardcoded ls
        "method": "GET",
        "note": "Runs ls on page load"
    },
    {
        "file": "12_flask_form.py",
        "port": 5000,
        "type": "http",
        "url_ls": "http://127.0.0.1:5000/",
        "url_aio": "http://127.0.0.1:5000/",
        "method": "POST",
        "data_ls": {"cmd": "ls"},
        "data_aio": {"cmd": "aio"},
        "note": "POST form"
    },
    {
        "file": "13_flask_template.py",
        "port": 5000,
        "type": "http",
        "url_ls": "http://127.0.0.1:5000/?cmd=ls",
        "url_aio": "http://127.0.0.1:5000/?cmd=aio",
        "method": "GET",
        "note": "Query param or POST form"
    },
    {
        "file": "14_http_server_buttons.py",
        "port": 8000,
        "type": "http",
        "url_ls": "http://127.0.0.1:8000/?c=ls",
        "url_aio": None,  # Blocked - only allows ls and time
        "method": "GET",
        "note": "Whitelist commands only (ls, time)"
    },
]

def wait_for_server(port, timeout=10):
    """Wait for server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=1)
            return True
        except:
            time.sleep(0.1)
    return False

def benchmark_request(url, method="GET", data=None, runs=5):
    """Run multiple requests and return average time."""
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        try:
            if method == "GET":
                r = requests.get(url, timeout=10)
            else:
                r = requests.post(url, data=data, timeout=10)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        except Exception as e:
            times.append(None)

    valid = [t for t in times if t is not None]
    if valid:
        return sum(valid) / len(valid)
    return None

def run_benchmark():
    """Run benchmarks for all candidates."""
    results = []
    cwd = os.path.dirname(os.path.abspath(__file__))
    candidates_dir = os.path.join(cwd, "candidates")

    for c in CANDIDATES:
        file_path = os.path.join(candidates_dir, c["file"])
        if not os.path.exists(file_path):
            print(f"  Skipping {c['file']} - file not found")
            continue

        print(f"\nTesting {c['file']}...")

        # Start server
        proc = subprocess.Popen(
            [sys.executable, file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )

        try:
            # Wait for server
            if not wait_for_server(c["port"]):
                print(f"  Server failed to start")
                results.append({
                    "file": c["file"],
                    "ls_time": None,
                    "aio_time": None,
                    "note": c.get("note", "")
                })
                continue

            time.sleep(0.5)  # Extra settle time

            # Benchmark ls
            if c.get("data_ls"):
                ls_time = benchmark_request(c["url_ls"], c["method"], c["data_ls"])
            elif c.get("data"):
                ls_time = benchmark_request(c["url_ls"], c["method"], c["data"])
            else:
                ls_time = benchmark_request(c["url_ls"], c["method"])

            # Benchmark aio
            aio_time = None
            if c.get("url_aio"):
                if c.get("data_aio"):
                    aio_time = benchmark_request(c["url_aio"], c["method"], c["data_aio"])
                else:
                    aio_time = benchmark_request(c["url_aio"], c["method"])

            results.append({
                "file": c["file"],
                "ls_time": ls_time,
                "aio_time": aio_time,
                "note": c.get("note", "")
            })

            if ls_time:
                print(f"  ls: {ls_time*1000:.2f}ms", end="")
            else:
                print(f"  ls: N/A", end="")
            if aio_time:
                print(f"  aio: {aio_time*1000:.2f}ms")
            else:
                print(f"  aio: N/A")

        finally:
            # Kill server
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except:
                proc.terminate()
            proc.wait()
            time.sleep(0.5)

    return results

def print_table(results):
    """Print results as markdown table."""
    print("\n" + "="*80)
    print("\n## Benchmark Results\n")
    print("| Candidate | ls (ms) | aio (ms) | Notes |")
    print("|-----------|---------|----------|-------|")
    for r in results:
        ls_str = f"{r['ls_time']*1000:.2f}" if r['ls_time'] else "N/A"
        aio_str = f"{r['aio_time']*1000:.2f}" if r['aio_time'] else "N/A"
        print(f"| {r['file']} | {ls_str} | {aio_str} | {r['note']} |")

if __name__ == "__main__":
    print("="*80)
    print("Web UI Candidate Benchmark")
    print("="*80)
    results = run_benchmark()
    print_table(results)
