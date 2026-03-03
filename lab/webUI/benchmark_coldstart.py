#!/usr/bin/env python3
"""
Benchmark cold start + bashrc optimization strategies.
Tests: server startup time, first request, subsequent requests.
Compares: full bashrc vs instant-exit bashrc with essential functions first.
"""
import subprocess, time, sys, os, signal, statistics, shutil

CANDIDATES = [
    {"file": "14_http_server_buttons.py", "port": 8000, "url": "http://127.0.0.1:8000/?c={cmd}", "name": "http-buttons"},
    {"file": "10_fastapi_query.py", "port": 8000, "url": "http://127.0.0.1:8000/?c={cmd}", "name": "fastapi-query"},
    {"file": "02_aiohttp_pty_terminal.py", "port": 8080, "url": "http://127.0.0.1:8080/exec", "json": True, "name": "aiohttp-pty"},
]

BASHRC_ORIGINAL = os.path.expanduser("~/.bashrc")
BASHRC_BACKUP = os.path.expanduser("~/.bashrc.bench_backup")

def get_aio_function():
    """Extract aio function from current bashrc."""
    with open(BASHRC_ORIGINAL) as f:
        content = f.read()
    # Find aio function
    start = content.find("aio()")
    if start == -1:
        start = content.find("aio ()")
    if start == -1:
        return None
    # Find closing brace
    brace_count = 0
    end = start
    in_func = False
    for i, c in enumerate(content[start:], start):
        if c == '{':
            brace_count += 1
            in_func = True
        elif c == '}':
            brace_count -= 1
            if in_func and brace_count == 0:
                end = i + 1
                break
    return content[start:end]

def create_instant_bashrc():
    """Create optimized bashrc: essential functions first, early exit for non-interactive."""
    aio_func = get_aio_function()
    if not aio_func:
        return False

    with open(BASHRC_ORIGINAL) as f:
        original = f.read()

    # Backup
    shutil.copy(BASHRC_ORIGINAL, BASHRC_BACKUP)

    # Create instant version: aio first, then early exit, then rest
    instant = f'''# INSTANT BASHRC - essential functions before interactive check
# aio function (needed by subprocess calls)
{aio_func}

# Early exit for non-interactive shells (subprocess/scripts) - 0.5ms vs 5ms+
[[ $- != *i* ]] && return

# === INTERACTIVE SHELL ONLY BELOW ===
'''
    # Remove aio function from rest to avoid duplication
    rest = original.replace(aio_func, "").replace("# aio instant startup (Stage 1: true 0ms) - Added by aio install", "")

    with open(BASHRC_ORIGINAL, 'w') as f:
        f.write(instant + rest)

    return True

def restore_bashrc():
    """Restore original bashrc."""
    if os.path.exists(BASHRC_BACKUP):
        shutil.copy(BASHRC_BACKUP, BASHRC_ORIGINAL)
        os.remove(BASHRC_BACKUP)

def wait_server(port, timeout=10):
    import requests
    for _ in range(int(timeout * 20)):
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=0.3)
            return True
        except:
            time.sleep(0.05)
    return False

def bench_coldstart(candidate, cmd="aio", runs=5):
    """Benchmark cold start: server startup + first request."""
    import requests
    cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "candidates")
    filepath = os.path.join(cwd, candidate["file"])

    results = {"startup": [], "first": [], "warm": []}

    for _ in range(runs):
        # Cold start
        t_start = time.perf_counter()
        proc = subprocess.Popen(
            [sys.executable, filepath],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid, cwd=cwd
        )

        if not wait_server(candidate["port"]):
            try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except: proc.terminate()
            continue

        startup_time = (time.perf_counter() - t_start) * 1000
        results["startup"].append(startup_time)

        # First request (cold)
        t_first = time.perf_counter()
        try:
            if candidate.get("json"):
                requests.post(candidate["url"], json={"cmd": cmd}, timeout=5)
            else:
                requests.get(candidate["url"].format(cmd=cmd), timeout=5)
        except:
            pass
        first_time = (time.perf_counter() - t_first) * 1000
        results["first"].append(first_time)

        # Warm requests (average of 10)
        warm_times = []
        for _ in range(10):
            t = time.perf_counter()
            try:
                if candidate.get("json"):
                    requests.post(candidate["url"], json={"cmd": cmd}, timeout=5)
                else:
                    requests.get(candidate["url"].format(cmd=cmd), timeout=5)
                warm_times.append((time.perf_counter() - t) * 1000)
            except:
                pass
        if warm_times:
            results["warm"].append(statistics.mean(warm_times))

        # Cleanup
        try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except: proc.terminate()
        proc.wait()
        time.sleep(0.3)

    return {
        "startup": statistics.mean(results["startup"]) if results["startup"] else 0,
        "first": statistics.mean(results["first"]) if results["first"] else 0,
        "warm": statistics.mean(results["warm"]) if results["warm"] else 0,
    }

def bench_bashrc_only():
    """Benchmark just the bashrc sourcing overhead."""
    results = {}

    # Full bashrc
    times = []
    for _ in range(20):
        t = time.perf_counter()
        subprocess.getoutput("source ~/.bashrc 2>/dev/null && echo done")
        times.append((time.perf_counter() - t) * 1000)
    results["full"] = min(times)

    # With aio
    times = []
    for _ in range(20):
        t = time.perf_counter()
        subprocess.getoutput("source ~/.bashrc 2>/dev/null && aio")
        times.append((time.perf_counter() - t) * 1000)
    results["full_aio"] = min(times)

    return results

def main():
    print("=" * 70)
    print("COLD START + BASHRC OPTIMIZATION BENCHMARK")
    print("=" * 70)

    # Test 1: Current bashrc overhead
    print("\n## Phase 1: Current Bashrc Overhead\n")
    current = bench_bashrc_only()
    print(f"source ~/.bashrc && echo: {current['full']:.2f}ms")
    print(f"source ~/.bashrc && aio:  {current['full_aio']:.2f}ms")

    # Test 2: Cold start with current bashrc
    print("\n## Phase 2: Cold Start (Current Bashrc)\n")
    print(f"{'Candidate':<15} {'Startup':>10} {'1st Req':>10} {'Warm':>10}")
    print("-" * 50)

    current_results = {}
    for c in CANDIDATES:
        r = bench_coldstart(c, runs=3)
        current_results[c["name"]] = r
        print(f"{c['name']:<15} {r['startup']:>8.1f}ms {r['first']:>8.2f}ms {r['warm']:>8.2f}ms")

    # Test 3: Create instant bashrc
    print("\n## Phase 3: Creating Instant Bashrc\n")
    if not create_instant_bashrc():
        print("Failed to create instant bashrc")
        return
    print("Created instant bashrc: aio() defined before [[ $- != *i* ]] && return")

    # Test 4: Instant bashrc overhead
    print("\n## Phase 4: Instant Bashrc Overhead\n")
    instant = bench_bashrc_only()
    print(f"source ~/.bashrc && echo: {instant['full']:.2f}ms")
    print(f"source ~/.bashrc && aio:  {instant['full_aio']:.2f}ms")
    print(f"Speedup: {current['full_aio']/instant['full_aio']:.1f}x")

    # Test 5: Cold start with instant bashrc
    print("\n## Phase 5: Cold Start (Instant Bashrc)\n")
    print(f"{'Candidate':<15} {'Startup':>10} {'1st Req':>10} {'Warm':>10}")
    print("-" * 50)

    instant_results = {}
    for c in CANDIDATES:
        r = bench_coldstart(c, runs=3)
        instant_results[c["name"]] = r
        print(f"{c['name']:<15} {r['startup']:>8.1f}ms {r['first']:>8.2f}ms {r['warm']:>8.2f}ms")

    # Restore original bashrc
    restore_bashrc()
    print("\n✓ Restored original bashrc")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: INSTANT BASHRC IMPROVEMENT")
    print("=" * 70)
    print(f"\n{'Metric':<25} {'Before':>12} {'After':>12} {'Speedup':>10}")
    print("-" * 60)
    print(f"{'bashrc + aio':<25} {current['full_aio']:>10.2f}ms {instant['full_aio']:>10.2f}ms {current['full_aio']/instant['full_aio']:>9.1f}x")

    for name in current_results:
        c_warm = current_results[name]["warm"]
        i_warm = instant_results[name]["warm"]
        speedup = c_warm / i_warm if i_warm > 0 else 0
        print(f"{name + ' warm req':<25} {c_warm:>10.2f}ms {i_warm:>10.2f}ms {speedup:>9.1f}x")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        restore_bashrc()
        print("\n✓ Restored bashrc")
    except Exception as e:
        restore_bashrc()
        raise
