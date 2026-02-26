"""a x.url <url> - open in browser on all devices"""
import sys, subprocess as sp
from concurrent.futures import ThreadPoolExecutor as TP, as_completed
from ssh import _load

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

def run():
    url = sys.argv[2] if len(sys.argv) > 2 else 'https://github.com/seanpattencode/a'
    if not url.startswith('http'): url = 'https://' + url
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

    with TP(8) as ex:
        for f in as_completed([ex.submit(_open, d) for d in hosts]):
            n, ok, info = f.result()
            print(f"{'✓' if ok else 'x'} {n}: {info}")

