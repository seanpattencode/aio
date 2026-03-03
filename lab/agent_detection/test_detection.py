#!/usr/bin/env python3
"""Compare agent readiness detection methods"""
import subprocess as sp, time, os, sys, random, resource

KEYWORDS = ["claude code", "welcome", "opus", "gemini", "codex", "try \""]
TIMEOUT = 20

def capture(sn):
    r = sp.run(["tmux", "capture-pane", "-t", sn, "-p", "-S", "-50"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""

def ready(out):
    return any(k in out.lower() for k in KEYWORDS)

def kill_sess(sn):
    sp.run(["tmux", "kill-session", "-t", sn], capture_output=True)
    time.sleep(0.2)

def cpu_time():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime

def test_poll(interval):
    sn = f"t{random.randint(10000,99999)}"
    cpu0 = cpu_time()
    sp.run(["tmux", "new-session", "-d", "-s", sn, "claude --dangerously-skip-permissions"], capture_output=True)
    time.sleep(0.1)

    start, polls = time.time(), 0
    out = ""
    for _ in range(int(TIMEOUT / interval)):
        out = capture(sn)
        polls += 1
        if ready(out):
            elapsed = time.time() - start
            cpu = cpu_time() - cpu0
            kill_sess(sn)
            return elapsed * 1000, cpu * 1000, polls, out
        time.sleep(interval)

    kill_sess(sn)
    return -1, 0, polls, out

def test_tight():
    sn = f"t{random.randint(10000,99999)}"
    cpu0 = cpu_time()
    sp.run(["tmux", "new-session", "-d", "-s", sn, "claude --dangerously-skip-permissions"], capture_output=True)
    time.sleep(0.1)

    start, polls = time.time(), 0
    out = ""
    while time.time() - start < TIMEOUT:
        out = capture(sn)
        polls += 1
        if ready(out):
            elapsed = time.time() - start
            cpu = cpu_time() - cpu0
            kill_sess(sn)
            return elapsed * 1000, cpu * 1000, polls, out

    kill_sess(sn)
    return -1, 0, polls, out

def test_control():
    sn = f"t{random.randint(10000,99999)}"
    cpu0 = cpu_time()
    sp.run(["tmux", "new-session", "-d", "-s", sn, "claude --dangerously-skip-permissions"], capture_output=True)
    time.sleep(0.1)

    start, polls = time.time(), 0
    proc = sp.Popen(["tmux", "-C", "attach", "-t", sn], stdout=sp.PIPE, stderr=sp.PIPE, text=True)

    out = ""
    try:
        while time.time() - start < TIMEOUT:
            proc.stdout.readline()
            out = capture(sn)
            polls += 1
            if ready(out):
                elapsed = time.time() - start
                cpu = cpu_time() - cpu0
                proc.terminate()
                kill_sess(sn)
                return elapsed * 1000, cpu * 1000, polls, out
    except:
        pass

    proc.terminate()
    kill_sess(sn)
    return -1, 0, polls, out

def proof(out):
    for line in out.split('\n'):
        if any(k in line.lower() for k in KEYWORDS):
            return line.strip()[:35]
    return ""

def main():
    print("Agent Detection Method Comparison")
    print("=" * 70)

    if sp.run(["which", "claude"], capture_output=True).returncode != 0:
        print("Error: claude not found"); sys.exit(1)

    results = []

    tests = [
        ("poll_0.5s", lambda: test_poll(0.5)),
        ("poll_0.2s", lambda: test_poll(0.2)),
        ("poll_0.1s", lambda: test_poll(0.1)),
        ("poll_0.05s", lambda: test_poll(0.05)),
        ("tight_loop", test_tight),
        ("control_mode", test_control),
    ]

    print("\nRunning tests (each spawns real claude instance)...\n")

    for name, fn in tests:
        print(f"  {name}...", end=" ", flush=True)
        ms, cpu, polls, out = fn()
        p = proof(out)
        if ms < 0:
            print("FAIL")
            results.append((name, -1, 0, 0, ""))
        else:
            print(f"{ms:.0f}ms ({polls} polls, {cpu:.0f}ms CPU)")
            results.append((name, ms, cpu, polls, p))

    print("\n" + "=" * 70)
    print(f"{'Method':<14} {'Latency':<10} {'CPU(ms)':<10} {'Polls':<8} {'Proof'}")
    print("-" * 70)
    for name, ms, cpu, polls, p in sorted(results, key=lambda x: x[1] if x[1] > 0 else 99999):
        lat = f"{ms:.0f}ms" if ms > 0 else "FAIL"
        print(f"{name:<14} {lat:<10} {cpu:<10.0f} {polls:<8} {p}")

    # Analysis
    baseline = next((r for r in results if r[0] == "tight_loop"), None)
    current = next((r for r in results if r[0] == "poll_0.5s"), None)
    if baseline and current and baseline[1] > 0 and current[1] > 0:
        print(f"\n--- Analysis ---")
        print(f"Agent startup time: ~{baseline[1]:.0f}ms")
        print(f"Current (0.5s poll) adds: ~{current[1] - baseline[1]:.0f}ms latency")
        print(f"Current CPU cost: {current[2]:.0f}ms ({current[3]} subprocess calls)")
        print(f"Tight loop CPU cost: {baseline[2]:.0f}ms ({baseline[3]} subprocess calls)")
        print(f"CPU ratio: {baseline[2]/current[2]:.1f}x more for tight loop")

    with open("/tmp/agent_detection_results.txt", "w") as f:
        for r in results:
            f.write(f"{r}\n")

if __name__ == "__main__":
    main()
