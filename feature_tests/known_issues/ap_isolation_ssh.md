# AP Isolation - SSH Unreachable Hosts

## Problem
SSH hosts (especially Termux on Android) appear unreachable from some devices but work fine from others on the same network.

## Symptoms
- `aio ssh` shows hosts as `x` (unreachable)
- Can ping router/gateway but not the target host
- Mac (WiFi) can reach Termux, but Linux PC (Ethernet) cannot
- 100% packet loss when pinging WiFi devices from wired connection

## Cause
**AP Isolation** (also called Client Isolation, WLAN Partition, or Wireless Isolation) is a router security feature that prevents:
- Wired (Ethernet) clients from communicating with Wireless (WiFi) clients
- Sometimes WiFi clients from communicating with each other

This is often enabled by default on consumer routers for security.

## Detection
`aio ssh` now auto-detects this condition:
```
! Unreachable hosts - check AP isolation (wired↔wifi blocked)
```

Logic: If gateway is pingable but some hosts aren't, suggests AP isolation.

## Solutions

### 1. Disable AP Isolation (Recommended)
1. Access router admin panel (usually http://192.168.1.1)
2. Find Wireless/WiFi settings
3. Look for: "AP Isolation", "Client Isolation", "WLAN Partition", or "Wireless Isolation"
4. Disable it
5. Save and reboot router if needed

### 2. Use Same Connection Type
- Connect the Linux PC to WiFi instead of Ethernet
- Or connect the phone/Termux via USB Ethernet adapter

### 3. Use a Jump Host
SSH through a device that can reach both networks:
```bash
ssh -J mac_user@mac_ip user@termux_ip -p 8022
```

## Sources
- [Termux SSH Connection Issues - GitHub #3544](https://github.com/termux/termux-app/issues/3544)
- [Termux SSH won't connect - GitHub #456](https://github.com/termux/termux-app/issues/456)
- [WLAN SSHD connection problems - e.foundation](https://community.e.foundation/t/termux-sshd-connection-problems-via-wlan/22736)
- [Can ping but can't SSH - AnswerOverflow](https://www.answeroverflow.com/m/1330659050798583829)
- [Termux SSH Guide - DEV Community](https://dev.to/chami/connecting-to-your-android-device-via-ssh-from-linux-a-complete-termux-guide-4lhd)
- [SSH Connection Timeout Fix - Veeble](https://www.veeble.com/kb/how-to-fix-connection-timed-out-in-ssh/)

## Related
- Termux uses port **8022** (not 22) because Android restricts privileged ports
- Password auth requires `sshpass` package on client
- Run `sshd` in Termux to start the SSH server
