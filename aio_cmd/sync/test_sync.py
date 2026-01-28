#!/usr/bin/env python3
"""Test note sync between local and remote"""
import subprocess as sp, random, string, base64

_pw = None
def run(host, code):
    """Run python code on host (None=local)"""
    if host is None:
        return sp.run(['python3', '-c', code], capture_output=True, text=True)
    hp = host.rsplit(':', 1)
    h, port = (hp[0], hp[1]) if len(hp) > 1 and hp[1].isdigit() else (host, '22')
    cmd = f'python3 << "EOF"\nimport sys,os; sys.path.insert(0, os.path.expanduser("~/.local/bin"))\n{code}\nEOF'
    ssh = (['sshpass', '-p', _pw] if _pw else []) + ['ssh', '-o', 'StrictHostKeyChecking=no', '-p', port, h, cmd]
    return sp.run(ssh, capture_output=True, text=True)

def test_sync(remote_host, pw=None):
    global _pw; _pw = pw
    rid = ''.join(random.choices(string.ascii_lowercase, k=6))

    # 1. Add note locally
    print(f"1. Adding note 'local_{rid}' locally...")
    r = run(None, f"""
from aio_cmd.sync import put, sync
put('notes', 'local_{rid}', {{'t': 'from local {rid}'}})
sync()
print('OK')
""")
    if 'OK' not in r.stdout: return print(f"FAIL: {r.stderr}")

    # 2. Check on remote
    print(f"2. Checking on {remote_host}...")
    r = run(remote_host, f"""
from aio_cmd.sync import sync, list_all
sync()
found = any(n.get('id') == 'local_{rid}' for n in list_all('notes'))
print('FOUND' if found else 'MISSING')
""")
    if 'FOUND' not in r.stdout: return print(f"FAIL: local→remote: {r.stderr or r.stdout}")
    print(f"   ✓ local→{remote_host}")

    # 3. Add note on remote
    print(f"3. Adding note 'remote_{rid}' on {remote_host}...")
    r = run(remote_host, f"""
from aio_cmd.sync import put, sync
put('notes', 'remote_{rid}', {{'t': 'from remote {rid}'}})
sync()
print('OK')
""")
    if 'OK' not in r.stdout: return print(f"FAIL: {r.stderr}")

    # 4. Check locally
    print(f"4. Checking locally...")
    r = run(None, f"""
from aio_cmd.sync import sync, list_all
sync()
found = any(n.get('id') == 'remote_{rid}' for n in list_all('notes'))
print('FOUND' if found else 'MISSING')
""")
    if 'FOUND' not in r.stdout: return print(f"FAIL: remote→local: {r.stderr or r.stdout}")
    print(f"   ✓ {remote_host}→local")

    print(f"\n✓ PASS: bidirectional sync works")

def get_host(name):
    """Get host string from ssh name"""
    import sqlite3, os
    c = sqlite3.connect(os.path.expanduser("~/.local/share/aios/aio.db"))
    r = c.execute("SELECT host,pw FROM ssh WHERE name=?", (name,)).fetchone()
    if not r: return name, None
    pw = base64.b64decode(r[1]).decode() if r[1] else None
    return r[0], pw

if __name__ == '__main__':
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else 'hsu'
    host, pw = get_host(name)
    test_sync(host, pw)
