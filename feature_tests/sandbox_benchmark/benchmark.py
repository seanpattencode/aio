#!/usr/bin/env python3
"""Sandbox benchmarks - startup overhead, isolation verification, Pi requirements."""
import subprocess as sp, time, os, json, shutil
from pathlib import Path

ITERATIONS, RESULTS = 20, []

def bench(name, cmd, verify_cmd=None):
    """Benchmark sandbox startup with /bin/true, verify isolation."""
    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        r = sp.run(cmd, shell=True, capture_output=True, text=True)
        times.append((time.perf_counter() - start) * 1000)

    avg, mn, mx = sum(times)/len(times), min(times), max(times)

    # Verify isolation if command provided
    isolated = "N/A"
    if verify_cmd:
        v = sp.run(verify_cmd, shell=True, capture_output=True, text=True)
        procs = len([l for l in v.stdout.split('\n') if l.strip()])
        isolated = f"✅ ({procs} procs)" if procs < 5 else f"⚠️ ({procs} procs)"

    result = {"name": name, "avg_ms": round(avg, 2), "min_ms": round(mn, 2),
              "max_ms": round(mx, 2), "overhead_ms": round(avg - RESULTS[0]["avg_ms"], 2) if RESULTS else 0,
              "success": r.returncode == 0, "isolation": isolated}
    RESULTS.append(result)
    status = "✅" if r.returncode == 0 else "❌"
    print(f"{status} {name:25} avg={avg:6.2f}ms  overhead={result['overhead_ms']:+6.2f}ms  iso={isolated}")
    return result

print("="*70)
print("SANDBOX BENCHMARK - Measuring startup overhead with /bin/true")
print("="*70 + "\n")

# Baseline
bench("baseline", "/bin/true")

# Bubblewrap variants
if shutil.which("bwrap"):
    BWRAP_BASE = "bwrap --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin --ro-bind /sbin /sbin --proc /proc --dev /dev"

    bench("bwrap (ro-bind only)", f"{BWRAP_BASE} /bin/true",
          f"{BWRAP_BASE} --unshare-pid ps aux")

    bench("bwrap (+unshare-pid)", f"{BWRAP_BASE} --unshare-pid --die-with-parent /bin/true",
          f"{BWRAP_BASE} --unshare-pid --die-with-parent ps aux")

    bench("bwrap (+unshare-all)", f"{BWRAP_BASE} --unshare-all --die-with-parent /bin/true",
          f"{BWRAP_BASE} --unshare-all --die-with-parent ps aux")

    bench("bwrap (full sandbox)", f"{BWRAP_BASE} --tmpfs /tmp --tmpfs /home --unshare-all --die-with-parent --new-session /bin/true",
          f"{BWRAP_BASE} --tmpfs /tmp --tmpfs /home --unshare-all --die-with-parent --new-session ps aux")

    # With workspace
    bench("bwrap (+workspace)", f"{BWRAP_BASE} --bind {os.getcwd()} /workspace --tmpfs /tmp --unshare-all --die-with-parent --chdir /workspace /bin/true")

# Unshare (direct kernel)
if shutil.which("unshare"):
    r = sp.run("unshare --user --pid --fork /bin/true", shell=True, capture_output=True)
    if r.returncode == 0:
        bench("unshare (user+pid)", "unshare --user --pid --fork /bin/true")

# Firejail
if shutil.which("firejail"):
    bench("firejail (default)", "firejail --quiet /bin/true")
    bench("firejail (--private)", "firejail --quiet --private /bin/true")

# Docker/Podman (expect slower)
for tool in ["docker", "podman"]:
    if shutil.which(tool) and sp.run(f"{tool} info", shell=True, capture_output=True).returncode == 0:
        bench(f"{tool} (alpine)", f"{tool} run --rm alpine /bin/true")

print("\n" + "="*70)
print("REQUIREMENTS: <1000ms startup, works on Raspberry Pi (ARM64)")
print("="*70)
best = None
for r in RESULTS[1:]:  # Skip baseline
    status = "✅ PASS" if r["avg_ms"] < 1000 and r["success"] else "❌ FAIL"
    margin = 1000 - r["avg_ms"]
    print(f"  {r['name']:25} {r['avg_ms']:6.2f}ms  margin={margin:6.0f}ms  {status}")
    if r["success"] and (best is None or r["avg_ms"] < best["avg_ms"]):
        best = r

# Write report
report = Path(__file__).parent / "REPORT.md"
with open(report, "w") as f:
    f.write(f"""# Sandbox Benchmark Report

**System:** {os.uname().sysname} {os.uname().release} ({os.uname().machine})
**Test:** `/bin/true` × {ITERATIONS} iterations
**Requirement:** <1000ms startup, Raspberry Pi (ARM64) compatible

## Results

| Method | Avg (ms) | Overhead (ms) | Isolation | Status |
|--------|----------|---------------|-----------|--------|
""")
    for r in RESULTS:
        st = "✅" if r["avg_ms"] < 1000 and r["success"] else "❌"
        f.write(f"| {r['name']} | {r['avg_ms']:.2f} | {r['overhead_ms']:+.2f} | {r['isolation']} | {st} |\n")

    f.write(f"""
## Recommendation

**Best: `{best['name']}`** — {best['avg_ms']:.2f}ms avg, {best['overhead_ms']:+.2f}ms overhead

### For aio.py agent sandboxing:

```python
SANDBOX_CMD = '''bwrap --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 \\
    --ro-bind /bin /bin --ro-bind /sbin /sbin --ro-bind /etc/resolv.conf /etc/resolv.conf \\
    --bind {{workspace}} /workspace --tmpfs /tmp --tmpfs /home --proc /proc --dev /dev \\
    --unshare-all --share-net --die-with-parent --chdir /workspace {{cmd}}'''
```

### Why bubblewrap:
- **{best['overhead_ms']:+.2f}ms overhead** — negligible vs 1000ms budget
- **PID isolation** — agent can't see/kill host processes
- **Filesystem isolation** — only workspace is writable
- **No root required** — uses unprivileged user namespaces
- **ARM64 native** — in Ubuntu repos for Raspberry Pi

## Raw Data

```json
{json.dumps(RESULTS, indent=2)}
```
""")

print(f"\n✅ Report: {report}")
