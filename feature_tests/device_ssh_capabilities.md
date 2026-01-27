# Device SSH Capabilities Report

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
