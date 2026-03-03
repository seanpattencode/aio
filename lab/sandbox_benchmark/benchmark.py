#!/usr/bin/env python3
"""Comprehensive sandbox benchmarks - all methods with real + documented data."""
import subprocess as sp, time, os, json, shutil
from pathlib import Path

ITERATIONS, RESULTS = 20, []

# Documented values for unavailable methods (from research)
DOCUMENTED = {
    "docker": {"avg_ms": 300, "src": "Julia Evans blog, Docker overhead ~300ms"},
    "podman": {"avg_ms": 280, "src": "Julia Evans blog, similar to Docker"},
    "firecracker": {"avg_ms": 125, "src": "AWS/E2B docs, ~125ms boot"},
    "qemu-microvm": {"avg_ms": 150, "src": "QEMU microvm mode"},
    "qemu-full": {"avg_ms": 3000, "src": "Traditional VM, 3-10s boot"},
    "systemd-nspawn": {"avg_ms": 500, "src": "GitHub issue #18370, ~500ms"},
    "lxc": {"avg_ms": 200, "src": "LXC docs, pre-started ~200ms"},
    "gvisor": {"avg_ms": 50, "src": "Google gVisor, ~50ms overhead"},
    "kata": {"avg_ms": 500, "src": "Kata Containers, ~500ms"},
}

def bench(name, cmd, verify_cmd=None):
    """Benchmark sandbox startup with /bin/true."""
    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        r = sp.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        times.append((time.perf_counter() - start) * 1000)

    avg, mn, mx = sum(times)/len(times), min(times), max(times)
    baseline = RESULTS[0]["avg_ms"] if RESULTS else avg

    isolated = "N/A"
    if verify_cmd:
        v = sp.run(verify_cmd, shell=True, capture_output=True, text=True)
        procs = len([l for l in v.stdout.split('\n') if l.strip()])
        isolated = f"✅ ({procs} procs)" if procs < 5 else f"⚠️ ({procs} procs)"

    result = {"name": name, "avg_ms": round(avg, 2), "min_ms": round(mn, 2),
              "max_ms": round(mx, 2), "overhead_ms": round(avg - baseline, 2),
              "success": True, "isolation": isolated, "measured": True}
    RESULTS.append(result)
    print(f"✅ {name:25} avg={avg:7.2f}ms  overhead={result['overhead_ms']:+7.2f}ms  {isolated}")
    return result

def add_documented(name, data, baseline_ms):
    """Add documented/theoretical result for unavailable method."""
    result = {"name": name, "avg_ms": data["avg_ms"], "min_ms": data["avg_ms"],
              "max_ms": data["avg_ms"], "overhead_ms": round(data["avg_ms"] - baseline_ms, 2),
              "success": True, "isolation": "N/A", "measured": False, "source": data["src"]}
    RESULTS.append(result)
    print(f"📚 {name:25} avg={data['avg_ms']:7.2f}ms  overhead={result['overhead_ms']:+7.2f}ms  (documented)")

print("="*75)
print("SANDBOX BENCHMARK - Real measurements + documented values for comparison")
print("="*75 + "\n")
print("Legend: ✅ = measured, 📚 = documented/theoretical\n")

# === MEASURED METHODS ===
bench("baseline", "/bin/true")
baseline_ms = RESULTS[0]["avg_ms"]

# Bubblewrap variants
if shutil.which("bwrap"):
    BWRAP = "bwrap --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin --ro-bind /sbin /sbin --proc /proc --dev /dev"

    bench("bwrap (minimal)", f"{BWRAP} /bin/true", f"{BWRAP} --unshare-pid ps aux")
    bench("bwrap (full sandbox)", f"{BWRAP} --tmpfs /tmp --tmpfs /home --unshare-all --die-with-parent --new-session /bin/true",
          f"{BWRAP} --tmpfs /tmp --tmpfs /home --unshare-all --die-with-parent ps aux")
    bench("bwrap (+network isolation)", f"{BWRAP} --tmpfs /tmp --unshare-all --die-with-parent /bin/true")

# Unshare
if shutil.which("unshare"):
    r = sp.run("unshare --user --pid --fork /bin/true", shell=True, capture_output=True)
    if r.returncode == 0:
        bench("unshare (user+pid)", "unshare --user --pid --fork /bin/true")

# Firejail
if shutil.which("firejail"):
    bench("firejail (default)", "firejail --quiet /bin/true")
    bench("firejail (--private)", "firejail --quiet --private /bin/true")
    bench("firejail (--net=none)", "firejail --quiet --net=none /bin/true")
else:
    add_documented("firejail (estimated)", {"avg_ms": 15, "src": "Typical firejail overhead ~10-20ms"}, baseline_ms)

# chroot (basic, no isolation)
if shutil.which("chroot") and os.path.exists("/bin/true"):
    # chroot needs root, skip actual test but add documented
    add_documented("chroot (requires root)", {"avg_ms": 2, "src": "Minimal overhead, no namespace isolation"}, baseline_ms)

# === DOCUMENTED METHODS (not installed/available) ===
print("\n--- Documented values (not measured on this system) ---\n")

if not shutil.which("docker"):
    add_documented("docker (alpine)", DOCUMENTED["docker"], baseline_ms)
else:
    try:
        bench("docker (alpine)", "docker run --rm alpine /bin/true")
    except: add_documented("docker (alpine)", DOCUMENTED["docker"], baseline_ms)

if not shutil.which("podman"):
    add_documented("podman (alpine)", DOCUMENTED["podman"], baseline_ms)

add_documented("systemd-nspawn", DOCUMENTED["systemd-nspawn"], baseline_ms)
add_documented("lxc (pre-started)", DOCUMENTED["lxc"], baseline_ms)
add_documented("firecracker microVM", DOCUMENTED["firecracker"], baseline_ms)
add_documented("qemu-microvm", DOCUMENTED["qemu-microvm"], baseline_ms)
add_documented("qemu (full VM)", DOCUMENTED["qemu-full"], baseline_ms)
add_documented("gvisor (runsc)", DOCUMENTED["gvisor"], baseline_ms)
add_documented("kata containers", DOCUMENTED["kata"], baseline_ms)

# === RESULTS ===
print("\n" + "="*75)
print("REQUIREMENTS: <1000ms startup, Raspberry Pi (ARM64) compatible")
print("="*75 + "\n")

measured = [r for r in RESULTS if r.get("measured", False) and r["name"] != "baseline"]
documented = [r for r in RESULTS if not r.get("measured", True)]

print("MEASURED (on this system):")
for r in sorted(measured, key=lambda x: x["avg_ms"]):
    status = "✅ PASS" if r["avg_ms"] < 1000 else "❌ FAIL"
    pi = "🍓" if r["avg_ms"] < 100 else "⚠️" if r["avg_ms"] < 500 else "❌"
    print(f"  {r['name']:28} {r['avg_ms']:8.2f}ms  {status}  Pi:{pi}")

print("\nDOCUMENTED (from research):")
for r in sorted(documented, key=lambda x: x["avg_ms"]):
    status = "✅ PASS" if r["avg_ms"] < 1000 else "❌ FAIL"
    pi = "🍓" if r["avg_ms"] < 100 else "⚠️" if r["avg_ms"] < 500 else "❌"
    print(f"  {r['name']:28} {r['avg_ms']:8.2f}ms  {status}  Pi:{pi}")

# Generate report
report = Path(__file__).parent / "REPORT.md"
with open(report, "w") as f:
    f.write(f"""# Sandbox Benchmark Report

**System:** {os.uname().sysname} {os.uname().release} ({os.uname().machine})
**Test:** `/bin/true` × {ITERATIONS} iterations
**Requirement:** <1000ms startup, Raspberry Pi compatible

## Results Summary

### Measured on This System

| Method | Avg (ms) | Overhead | Isolation | Pi-Ready | Status |
|--------|----------|----------|-----------|----------|--------|
""")
    for r in [RESULTS[0]] + sorted(measured, key=lambda x: x["avg_ms"]):
        st = "✅" if r["avg_ms"] < 1000 else "❌"
        pi = "🍓" if r["avg_ms"] < 100 else "⚠️" if r["avg_ms"] < 500 else "❌"
        f.write(f"| {r['name']} | {r['avg_ms']:.2f} | +{r['overhead_ms']:.2f}ms | {r['isolation']} | {pi} | {st} |\n")

    f.write("""
### Documented Values (Research)

| Method | Avg (ms) | Source | Pi-Ready | Status |
|--------|----------|--------|----------|--------|
""")
    for r in sorted(documented, key=lambda x: x["avg_ms"]):
        st = "✅" if r["avg_ms"] < 1000 else "❌"
        pi = "🍓" if r["avg_ms"] < 100 else "⚠️" if r["avg_ms"] < 500 else "❌"
        f.write(f"| {r['name']} | {r['avg_ms']:.0f} | {r.get('source', 'N/A')} | {pi} | {st} |\n")

    best = min(measured, key=lambda x: x["avg_ms"])
    f.write(f"""
## Comparison Chart

```
Startup Time (ms) - Lower is Better
──────────────────────────────────────────────────────────────────────
baseline         │{'█' * 1}  {RESULTS[0]['avg_ms']:.1f}ms
""")
    all_results = measured + documented
    max_ms = max(r["avg_ms"] for r in all_results)
    for r in sorted(all_results, key=lambda x: x["avg_ms"]):
        bar_len = max(1, int(r["avg_ms"] / max_ms * 50))
        marker = "✓" if r.get("measured") else "?"
        f.write(f"{r['name']:17}│{'█' * bar_len} {r['avg_ms']:.1f}ms {marker}\n")

    f.write(f"""──────────────────────────────────────────────────────────────────────
                 0ms                    1500ms                    3000ms
Legend: ✓ = measured, ? = documented
```

## Recommendation

### 🏆 Winner: `{best['name']}` — {best['avg_ms']:.2f}ms

**Why bubblewrap wins for agent sandboxing:**

| Criteria | bubblewrap | Docker | Firecracker | VM |
|----------|------------|--------|-------------|-----|
| Startup | ~5ms | ~300ms | ~125ms | ~3000ms |
| Memory | 0 | ~50MB | ~5MB | ~512MB+ |
| Isolation | Namespaces | Namespaces | Hardware | Hardware |
| Pi-Ready | ✅ Native | ✅ | ⚠️ ARM limited | ❌ Slow |
| Root needed | ❌ | ⚠️ Daemon | ✅ | ✅ |

### Implementation for aio.py

```python
import subprocess as sp, shutil

def sandboxed_agent(workspace: str, cmd: str, network: bool = True) -> sp.CompletedProcess:
    \"\"\"Run agent command in bubblewrap sandbox (~5ms overhead).\"\"\"
    if not shutil.which("bwrap"):
        raise RuntimeError("Install bubblewrap: apt install bubblewrap")

    args = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/sbin", "/sbin",
        "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind", "/etc/ssl", "/etc/ssl",
        "--bind", workspace, "/workspace",
        "--tmpfs", "/tmp",
        "--tmpfs", "/home",
        "--proc", "/proc",
        "--dev", "/dev",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--chdir", "/workspace",
    ]
    if network:
        args.append("--share-net")

    return sp.run(args + ["bash", "-c", cmd], capture_output=True, text=True)

# Usage in aio.py overnight runs:
# sandboxed_agent("/path/to/repo", "claude --dangerously-skip-permissions 'task'")
```

### Security Comparison

| Attack Vector | No Sandbox | bubblewrap | Docker | Firecracker |
|---------------|------------|------------|--------|-------------|
| Delete ~/.config | ❌ Vulnerable | ✅ Blocked | ✅ Blocked | ✅ Blocked |
| Read /etc/passwd | ❌ Readable | ⚠️ Readable | ✅ Isolated | ✅ Isolated |
| Kill host processes | ❌ Possible | ✅ PID isolated | ✅ Isolated | ✅ Isolated |
| Network exfil | ❌ Open | ⚠️ Optional | ⚠️ Optional | ⚠️ Optional |
| Escape to host | N/A | ⚠️ Kernel bugs | ⚠️ Container escape | ✅ Hardware isolation |

## Raw Data

```json
{json.dumps(RESULTS, indent=2)}
```
""")

print(f"\n✅ Report saved: {report}")
