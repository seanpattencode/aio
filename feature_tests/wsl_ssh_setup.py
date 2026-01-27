#!/usr/bin/env python3
"""WSL SSH Setup - run on WSL to enable SSH access from LAN"""
import sys, os, subprocess as sp, getpass, re

if not os.path.exists('/proc/version') or 'microsoft' not in open('/proc/version').read().lower():
    sys.exit("x Not WSL")

WSL_IP = sp.run("hostname -I", shell=True, capture_output=True, text=True).stdout.split()[0]
WIN_IP = re.search(r'192\.168\.1\.\d+', sp.run(["powershell.exe", "-c", "ipconfig"], capture_output=True, text=True).stdout)
WIN_IP = WIN_IP.group() if WIN_IP else None
print(f"WSL: {WSL_IP}  Windows: {WIN_IP}")
if not WIN_IP: sys.exit("x No Windows LAN IP (192.168.1.x) found")

sp.run("pgrep -x sshd >/dev/null || sudo service ssh start", shell=True)

# Write PS1 script to Windows temp
ps1 = f'''netsh interface portproxy delete v4tov4 listenport=2222 listenaddress=0.0.0.0 2>$null
netsh interface portproxy add v4tov4 listenport=2222 listenaddress=0.0.0.0 connectport=22 connectaddress={WSL_IP}
netsh advfirewall firewall delete rule name="WSL SSH" 2>$null
netsh advfirewall firewall add rule name="WSL SSH" dir=in action=allow protocol=tcp localport=2222
Write-Host "=== Port Forward ===" -ForegroundColor Green
netsh interface portproxy show all
Write-Host "=== Firewall Rule ===" -ForegroundColor Green
netsh advfirewall firewall show rule name="WSL SSH"
pause'''
ps1_path = "/mnt/c/Windows/Temp/wsl_ssh_setup.ps1"
open(ps1_path, "w").write(ps1)
print("=== Running admin setup (check Windows for UAC) ===")
sp.run(["powershell.exe", "-c", "Start-Process powershell -Verb RunAs -ArgumentList '-ExecutionPolicy','Bypass','-File','C:\\Windows\\Temp\\wsl_ssh_setup.ps1'"])
input("Press Enter after Windows shows 'Firewall Rule' result...")

# Verify
pf = sp.run(["powershell.exe", "-c", "netsh interface portproxy show all"], capture_output=True, text=True).stdout
if "2222" not in pf: sys.exit("x Port forward not set")
print("✓ Port forward OK")

# Register
name = sys.argv[1] if len(sys.argv) > 1 else f"wsl-{os.uname().nodename}"
host = f"{getpass.getuser()}@{WIN_IP}:2222"
print(f"Registering: {name} = {host}")
pw = getpass.getpass("SSH password: ")

sys.path.insert(0, os.path.expanduser("~/aio"))
from aio_cmd._common import init_db, db, emit_event
from aio_cmd.ssh import _enc
init_db(); c = db(); c.execute("DELETE FROM ssh WHERE name=?", (name,)); c.execute("INSERT INTO ssh(name,host,pw)VALUES(?,?,?)", (name, host, _enc(pw))); c.commit()
emit_event("ssh", "add", {"name": name, "host": host, "pw": _enc(pw)}, sync=True)
print(f"✓ {name} = {host}\nTest: aio ssh {name}")
