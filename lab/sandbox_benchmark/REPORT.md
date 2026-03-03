# Sandbox Benchmark Report

**System:** Linux 6.17.0-8-generic (x86_64)
**Test:** `/bin/true` x 20 iterations
**Requirement:** <1000ms startup, Raspberry Pi compatible

---

## Methods Tested

| Method | How It Works |
|--------|--------------|
| baseline | Direct process execution with no isolation. |
| unshare | Linux syscall that creates new namespaces (PID, user, mount) for process isolation without containerization. |
| bubblewrap (bwrap) | Unprivileged sandboxing tool using Linux namespaces and bind mounts; used by Flatpak and Chrome. |
| firejail | SUID sandbox that applies seccomp filters and namespace isolation with pre-built profiles for common apps. |
| chroot | Changes the root directory for a process; oldest Unix isolation but no namespace separation. |
| gvisor | Google's user-space kernel that intercepts syscalls and runs them in a sandboxed Go runtime. |
| Docker | Container runtime using namespaces + cgroups + overlay filesystem with a daemon managing container lifecycle. |
| Podman | Daemonless Docker alternative that runs containers as regular user processes. |
| LXC | System containers that run full Linux userspace with shared kernel, heavier than app containers. |
| systemd-nspawn | systemd's container tool for running full OS trees with namespace isolation. |
| Firecracker | AWS microVM using KVM hardware virtualization with minimal device model for ~125ms boot. |
| QEMU microvm | Minimal QEMU configuration with reduced device emulation for faster VM startup. |
| QEMU (full) | Traditional full-system emulator with complete hardware virtualization. |
| Kata Containers | Runs containers inside lightweight VMs for hardware-level isolation. |

---

## Results: Measured on This System

| Method                     | Avg (ms) | Overhead    | Isolated | Pi-Ready | Status |
|----------------------------|----------|-------------|----------|----------|--------|
| baseline                   | 0.98     | +0.00ms     | No       | Yes      | PASS   |
| unshare (user+pid)         | 1.52     | +0.54ms     | PID only | Yes      | PASS   |
| bwrap (minimal)            | 4.63     | +3.65ms     | Yes      | Yes      | PASS   |
| bwrap (+network isolation) | 5.19     | +4.21ms     | Yes      | Yes      | PASS   |
| bwrap (full sandbox)       | 5.20     | +4.22ms     | Yes      | Yes      | PASS   |

## Results: Documented Values (Research)

| Method              | Avg (ms) | Source                          | Pi-Ready | Status |
|---------------------|----------|---------------------------------|----------|--------|
| chroot              | 2        | Minimal overhead, no namespaces | Yes      | PASS   |
| firejail            | 15       | Typical overhead ~10-20ms       | Yes      | PASS   |
| gvisor (runsc)      | 50       | Google gVisor docs              | Yes      | PASS   |
| firecracker microVM | 125      | AWS/E2B docs                    | Limited  | PASS   |
| qemu-microvm        | 150      | QEMU microvm mode               | Limited  | PASS   |
| lxc (pre-started)   | 200      | LXC documentation               | Limited  | PASS   |
| podman (alpine)     | 280      | Julia Evans blog                | Limited  | PASS   |
| docker (alpine)     | 300      | Julia Evans blog                | Limited  | PASS   |
| systemd-nspawn      | 500      | GitHub issue #18370             | No       | PASS   |
| kata containers     | 500      | Kata Containers docs            | No       | PASS   |
| qemu (full VM)      | 3000     | Traditional VM boot             | No       | FAIL   |

---

## Comparison Chart

```
Method                  Time (ms)   Bar
----------------------  ---------   ----------------------------------------
baseline                    1.0     #
unshare                     1.5     #
chroot                      2.0     #
bwrap (minimal)             4.6     #
bwrap (full)                5.2     #
firejail                   15.0     #
gvisor                     50.0     ##
firecracker               125.0     ####
qemu-microvm              150.0     #####
lxc                       200.0     #######
podman                    280.0     #########
docker                    300.0     ##########
systemd-nspawn            500.0     #################
kata                      500.0     #################
qemu (full VM)           3000.0     ################################# [FAILS]
                                    |         |         |         |
                                    0       250       500      1000ms (limit)
```

---

## Recommendation

**Winner: bubblewrap (bwrap)** at 5.2ms with full isolation.

While `unshare` is faster (1.5ms), bubblewrap provides easier filesystem controls and is what Anthropic uses for Claude Code sandboxing.

### Comparison Table

| Criteria      | bubblewrap | Docker  | Firecracker | Full VM  |
|---------------|------------|---------|-------------|----------|
| Startup       | 5ms        | 300ms   | 125ms       | 3000ms   |
| Memory        | 0          | ~50MB   | ~5MB        | ~512MB+  |
| Isolation     | Namespaces | Namespaces | Hardware | Hardware |
| Pi-Ready      | Yes        | Yes     | Limited     | No       |
| Root needed   | No         | Daemon  | Yes         | Yes      |

### Security Comparison

| Attack Vector        | No Sandbox | bubblewrap | Docker  | Firecracker |
|----------------------|------------|------------|---------|-------------|
| Delete ~/.config     | Vulnerable | Blocked    | Blocked | Blocked     |
| Read /etc/passwd     | Readable   | Readable   | Isolated| Isolated    |
| Kill host processes  | Possible   | Blocked    | Blocked | Blocked     |
| Network exfiltration | Open       | Optional   | Optional| Optional    |
| Escape to host       | N/A        | Kernel bug | Container escape | Hardware isolated |

---

## Implementation for aio.py

```python
import subprocess as sp, shutil

def sandboxed_agent(workspace: str, cmd: str, network: bool = True) -> sp.CompletedProcess:
    """Run agent command in bubblewrap sandbox (~5ms overhead)."""
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
```

---

## Raw Data

See benchmark.py for full JSON output.
