# Sandbox Benchmark Report

**System:** Linux 6.17.0-8-generic (x86_64)
**Test:** `/bin/true` × 20 iterations
**Requirement:** <1000ms startup, Raspberry Pi (ARM64) compatible

## Results

| Method | Avg (ms) | Overhead (ms) | Isolation | Status |
|--------|----------|---------------|-----------|--------|
| baseline | 1.00 | +0.00 | N/A | ✅ |
| bwrap (ro-bind only) | 4.69 | +3.69 | ✅ (3 procs) | ✅ |
| bwrap (+unshare-pid) | 4.62 | +3.62 | ✅ (3 procs) | ✅ |
| bwrap (+unshare-all) | 5.10 | +4.10 | ✅ (3 procs) | ✅ |
| bwrap (full sandbox) | 5.12 | +4.12 | ✅ (3 procs) | ✅ |
| bwrap (+workspace) | 5.26 | +4.26 | N/A | ✅ |
| unshare (user+pid) | 1.59 | +0.59 | N/A | ✅ |

## Recommendation

### Fastest: `unshare` — 1.59ms (+0.59ms overhead)
Basic PID/user namespace isolation. Requires manual mount setup.

### Best for agents: `bwrap (full sandbox)` — 5.12ms (+4.12ms overhead)
Complete isolation with easy filesystem controls. **This is what Claude Code uses.**

### For aio.py agent sandboxing:

```python
def sandboxed_run(workspace: str, cmd: str) -> subprocess.CompletedProcess:
    """Run command in bubblewrap sandbox (~5ms overhead)."""
    return subprocess.run([
        "bwrap",
        "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64", "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/sbin", "/sbin", "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind", "/etc/ssl", "/etc/ssl",  # HTTPS certs
        "--bind", workspace, "/workspace",
        "--tmpfs", "/tmp", "--tmpfs", "/home",
        "--proc", "/proc", "--dev", "/dev",
        "--unshare-all", "--share-net", "--die-with-parent",
        "--chdir", "/workspace",
        "bash", "-c", cmd
    ])
```

### Why bubblewrap over unshare:
- **+4.12ms overhead** — still 195x faster than 1000ms requirement
- **Verified PID isolation** — only 3 processes visible (sandbox + bwrap + cmd)
- **Filesystem isolation** — `/home` is tmpfs, only workspace writable
- **Easy bind mounts** — simple CLI vs manual mount syscalls
- **No root required** — uses unprivileged user namespaces
- **ARM64 native** — `apt install bubblewrap` on Raspberry Pi

## Raw Data

```json
[
  {
    "name": "baseline",
    "avg_ms": 1.0,
    "min_ms": 0.87,
    "max_ms": 1.38,
    "overhead_ms": 0,
    "success": true,
    "isolation": "N/A"
  },
  {
    "name": "bwrap (ro-bind only)",
    "avg_ms": 4.69,
    "min_ms": 4.0,
    "max_ms": 5.19,
    "overhead_ms": 3.69,
    "success": true,
    "isolation": "\u2705 (3 procs)"
  },
  {
    "name": "bwrap (+unshare-pid)",
    "avg_ms": 4.62,
    "min_ms": 4.15,
    "max_ms": 5.1,
    "overhead_ms": 3.62,
    "success": true,
    "isolation": "\u2705 (3 procs)"
  },
  {
    "name": "bwrap (+unshare-all)",
    "avg_ms": 5.1,
    "min_ms": 4.04,
    "max_ms": 6.64,
    "overhead_ms": 4.1,
    "success": true,
    "isolation": "\u2705 (3 procs)"
  },
  {
    "name": "bwrap (full sandbox)",
    "avg_ms": 5.12,
    "min_ms": 4.15,
    "max_ms": 5.91,
    "overhead_ms": 4.12,
    "success": true,
    "isolation": "\u2705 (3 procs)"
  },
  {
    "name": "bwrap (+workspace)",
    "avg_ms": 5.26,
    "min_ms": 4.69,
    "max_ms": 6.17,
    "overhead_ms": 4.26,
    "success": true,
    "isolation": "N/A"
  },
  {
    "name": "unshare (user+pid)",
    "avg_ms": 1.59,
    "min_ms": 1.4,
    "max_ms": 1.73,
    "overhead_ms": 0.59,
    "success": true,
    "isolation": "N/A"
  }
]
```
