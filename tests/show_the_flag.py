#!/usr/bin/env python3
"""Test: Open a URL on all devices - each OS uses different browser command"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from a_cmd.ssh import _load
from a_cmd._common import _up
import subprocess as sp
from concurrent.futures import ThreadPoolExecutor as TP

# OS-specific browser commands (detected from OS field)
def _browser_cmd(os_info, url):
    os_info = (os_info or '').lower()
    if 'darwin' in os_info:
        return f'open "{url}"'
    elif 'android' in os_info:
        return f'termux-open-url "{url}"'
    elif 'microsoft' in os_info or 'wsl' in os_info:
        return f'/mnt/c/Windows/System32/cmd.exe /c start {url}'
    else:  # Linux
        return f'xdg-open "{url}" 2>/dev/null || sensible-browser "{url}" 2>/dev/null || echo "no browser"'

def run(url):
    hosts = _load()
    print(f"Opening: {url}\n")

    def _open(d):
        n, h, pw, os_info = d.get('Name'), d.get('Host'), d.get('Password'), d.get('OS')
        if not h: return (n, False, 'no host')
        hp = h.rsplit(':', 1)
        cmd = _browser_cmd(os_info, url)
        r = sp.run(
            (['sshpass', '-p', pw] if pw else []) +
            ['ssh', '-oConnectTimeout=5', '-oStrictHostKeyChecking=no'] +
            (['-p', hp[1]] if len(hp) > 1 else []) +
            [hp[0], cmd],
            capture_output=True, text=True
        )
        return (n, r.returncode == 0, os_info or '?')

    for n, ok, info in TP(8).map(_open, hosts):
        print(f"{'✓' if ok else 'x'} {n}: {info}")

if __name__ == '__main__':
    url = sys.argv[1] if len(sys.argv) > 1 else 'https://github.com/seanpattencode/aio'
    run(url)
