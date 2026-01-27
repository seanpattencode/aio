# Device SSH Capabilities Report

## Why SSH

The minimal path from intent to execution:

```
Human intent
    ↓
Terminal (text in, text out)
    ↓
Kernel (syscalls)
    ↓
CPU (instructions)
    ↓
Physics (electrons)
```

- Kernel: heart of the system, Turing-complete access to CPU/chips
- Terminal: direct path to kernel
- SSH: direct path to kernel over network

Everything else - GUIs, REST APIs, cloud platforms - are abstractions on top. Sometimes useful, often just toll booths. SSH is the raw path to any Turing-complete machine. The capability existed since 1995; we just got distracted by walled gardens.

Multi-device control was inevitable the moment people had more than one PC. We just never normalized it.

## Current Fleet
- Linux (Ubuntu) - full support
- Android (Termux) - full support
- Windows (WSL) - full support via port forward
- macOS - full support
- Remote servers - full support

## Expansion Candidates

### Smartwatch (Wear OS)
| Factor | Assessment |
|--------|------------|
| Termux support | No official support, sideload unreliable |
| Battery | ~300mAh, SSH daemon drains in hours |
| CPU/RAM | Weak (Snapdragon Wear), 1-2GB RAM |
| Lag | Significant, impractical for real work |
| Input | Tiny screen, no keyboard |
| **Verdict** | **Not practical** |

**Alternative:** Watch sends commands to phone via Wear OS APIs, phone relays to fleet.

### Android TV
| Factor | Assessment |
|--------|------------|
| Termux support | Works via sideload |
| Battery | Always plugged in, not a concern |
| CPU/RAM | Decent (Shield: Tegra X1, 3GB) |
| Lag | Minimal, runs like cheap Linux box |
| Input | BT keyboard or headless via SSH |
| **Verdict** | **Practical for always-on tasks** |

**Use cases:** Home automation hub, media server control, always-on agent host.

### Raspberry Pi / SBC
| Factor | Assessment |
|--------|------------|
| SSH support | Native Linux, full support |
| Power | 5-15W, always-on viable |
| CPU/RAM | Pi 5: quad-core, 8GB RAM |
| Lag | None, proper Linux |
| **Verdict** | **Excellent** |

### iOS (iPhone/iPad)
| Factor | Assessment |
|--------|------------|
| Termux support | No, Apple restrictions |
| SSH client | Available (Blink, Termius) |
| SSH server | Jailbreak required |
| **Verdict** | **Client only without jailbreak** |

## Recommended Fleet Topology
```
                    [Cloud: HSU server]
                           |
    [Desktop]---[Phone/Termux]---[Android TV]
        |              |
      [WSL]      [Raspberry Pi]
```

Phone as mobile hub, desktops for heavy work, TV/Pi for always-on tasks.
