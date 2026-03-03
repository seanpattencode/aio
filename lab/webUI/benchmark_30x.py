#!/usr/bin/env python3
"""Benchmark all web UI candidates 30 times each for accurate comparison."""
import subprocess, time, sys, os, signal, statistics

CANDIDATES = [
    {"file": "02_aiohttp_pty_terminal.py", "port": 8080, "method": "POST", "url": "http://127.0.0.1:8080/exec", "json": True, "name": "aiohttp-pty"},
    {"file": "03_aiohttp_ws_timing.py", "port": 8080, "method": "GET", "url": "http://127.0.0.1:8080/", "name": "aiohttp-ws"},
    {"file": "06_flask_basic.py", "port": 5000, "method": "POST", "url": "http://127.0.0.1:5000/run", "name": "flask-basic"},
    {"file": "08_fastapi_basic.py", "port": 8000, "method": "GET", "url": "http://127.0.0.1:8000/", "name": "fastapi-basic"},
    {"file": "10_fastapi_query.py", "port": 8000, "method": "GET", "url": "http://127.0.0.1:8000/?c={cmd}", "name": "fastapi-query"},
    {"file": "11_http_server_basic.py", "port": 8000, "method": "GET", "url": "http://127.0.0.1:8000/", "name": "http-basic"},
    {"file": "12_flask_form.py", "port": 5000, "method": "POST", "url": "http://127.0.0.1:5000/", "form": True, "name": "flask-form"},
    {"file": "13_flask_template.py", "port": 5000, "method": "GET", "url": "http://127.0.0.1:5000/?cmd={cmd}", "name": "flask-template"},
    {"file": "14_http_server_buttons.py", "port": 8000, "method": "GET", "url": "http://127.0.0.1:8000/?c={cmd}", "name": "http-buttons"},
]

RUNS = 30

def wait_server(port, timeout=8):
    import requests
    for _ in range(int(timeout * 10)):
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=0.5)
            return True
        except: time.sleep(0.1)
    return False

def bench(candidate, cmd, runs=RUNS):
    import requests
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        try:
            if candidate.get("json"):
                requests.post(candidate["url"], json={"cmd": cmd}, timeout=5)
            elif candidate.get("form"):
                requests.post(candidate["url"], data={"cmd": cmd}, timeout=5)
            elif candidate["method"] == "POST":
                requests.post(candidate["url"], data={"cmd": cmd}, timeout=5)
            else:
                url = candidate["url"].format(cmd=cmd) if "{cmd}" in candidate["url"] else candidate["url"]
                requests.get(url, timeout=5)
            times.append((time.perf_counter() - t) * 1000)
        except Exception as e:
            pass
    return times

def run_all():
    import requests
    results = []
    cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "candidates")

    for c in CANDIDATES:
        filepath = os.path.join(cwd, c["file"])
        if not os.path.exists(filepath):
            print(f"Skipping {c['name']} - not found")
            continue

        print(f"\nTesting {c['name']} ({RUNS} runs each)...", flush=True)

        proc = subprocess.Popen(
            [sys.executable, filepath],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid, cwd=cwd
        )

        try:
            if not wait_server(c["port"]):
                print(f"  Failed to start")
                continue
            time.sleep(0.3)

            # Test ls
            ls_times = bench(c, "ls")
            # Test aio
            aio_times = bench(c, "aio") if "{cmd}" in c["url"] or c.get("json") or c.get("form") else []

            if ls_times:
                results.append({
                    "name": c["name"],
                    "file": c["file"],
                    "port": c["port"],
                    "url": c["url"].replace("{cmd}", "ls"),
                    "ls_min": min(ls_times),
                    "ls_avg": statistics.mean(ls_times),
                    "ls_std": statistics.stdev(ls_times) if len(ls_times) > 1 else 0,
                    "aio_min": min(aio_times) if aio_times else None,
                    "aio_avg": statistics.mean(aio_times) if aio_times else None,
                    "aio_std": statistics.stdev(aio_times) if len(aio_times) > 1 else None,
                    "supports_cmd": bool(aio_times),
                })
                print(f"  ls:  {min(ls_times):.2f}ms (min)  {statistics.mean(ls_times):.2f}ms (avg)")
                if aio_times:
                    print(f"  aio: {min(aio_times):.2f}ms (min)  {statistics.mean(aio_times):.2f}ms (avg)")
        finally:
            try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except: proc.terminate()
            proc.wait()
            time.sleep(0.5)

    return results

def print_results(results):
    # Sort by aio_min (fastest first), then ls_min for those without aio support
    results_aio = sorted([r for r in results if r["aio_min"]], key=lambda x: x["aio_min"])
    results_ls = sorted([r for r in results if not r["aio_min"]], key=lambda x: x["ls_min"])

    print("\n" + "=" * 80)
    print("RESULTS: RANKED BY SPEED (30 runs each)")
    print("=" * 80)

    print("\n## Candidates Supporting Arbitrary Commands (ranked by aio speed)\n")
    print("| Rank | Candidate | ls min | ls avg | aio min | aio avg | Port |")
    print("|------|-----------|--------|--------|---------|---------|------|")
    for i, r in enumerate(results_aio, 1):
        print(f"| {i} | {r['name']} | {r['ls_min']:.2f}ms | {r['ls_avg']:.2f}ms | {r['aio_min']:.2f}ms | {r['aio_avg']:.2f}ms | {r['port']} |")

    if results_ls:
        print("\n## Candidates with Hardcoded Commands (ranked by ls speed)\n")
        print("| Rank | Candidate | ls min | ls avg | Port |")
        print("|------|-----------|--------|--------|------|")
        for i, r in enumerate(results_ls, 1):
            print(f"| {i} | {r['name']} | {r['ls_min']:.2f}ms | {r['ls_avg']:.2f}ms | {r['port']} |")

    print("\n" + "=" * 80)
    print("URLs TO TRY")
    print("=" * 80)
    print("\n```")
    for r in results:
        url = r["url"]
        if r["supports_cmd"]:
            url_aio = r["url"].replace("ls", "aio").replace("{cmd}", "aio")
            print(f"{r['name']:<20} http://127.0.0.1:{r['port']}/")
            print(f"{'':20} {url_aio}")
        else:
            print(f"{r['name']:<20} http://127.0.0.1:{r['port']}/")
    print("```")

    # Winner
    if results_aio:
        winner = results_aio[0]
        print(f"\n🏆 FASTEST FOR ARBITRARY COMMANDS: {winner['name']}")
        print(f"   aio: {winner['aio_min']:.2f}ms | ls: {winner['ls_min']:.2f}ms | Port: {winner['port']}")

if __name__ == "__main__":
    results = run_all()
    print_results(results)
