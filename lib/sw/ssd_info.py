#!/usr/bin/env python3
"""Read-only SSD information checker."""
import subprocess, re

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def get_ssds():
    ssds = []
    for line in run("lsblk -d -o NAME,ROTA,TYPE").splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "0" and parts[2] == "disk" and not parts[0].startswith("loop"):
            ssds.append(parts[0])
    return ssds

def get_info(dev):
    info = {"device": f"/dev/{dev}"}
    udev = run(f"udevadm info -q all -n /dev/{dev}")

    patterns = {
        "model": r"E: ID_MODEL=(.+)", "vendor": r"E: ID_VENDOR=(.+)",
        "serial_raw": r"E: ID_SERIAL_SHORT=(.+)", "revision": r"E: ID_REVISION=(.+)",
        "transport": r"E: ID_BUS=(.+)", "driver": r"E: ID_USB_DRIVER=(.+)"
    }
    for k, p in patterns.items():
        if m := re.search(p, udev): info[k] = m.group(1)

    info["size"] = run(f"lsblk -d -o SIZE -n /dev/{dev}")

    # Decode hex serial
    if s := info.get("serial_raw"):
        try: info["serial"] = bytes.fromhex(s).decode("ascii")
        except: info["serial"] = s

    # SMART health
    smart = run(f"sudo smartctl -H /dev/{dev} 2>/dev/null")
    if "PASSED" in smart: info["health"] = "PASSED"
    elif "FAILED" in smart: info["health"] = "FAILED"

    return info

if __name__ == "__main__":
    for dev in get_ssds() or [print("No SSDs found")]:
        if dev:
            print(f"\n{'='*40}")
            for k, v in get_info(dev).items(): print(f"{k:12}: {v}")
