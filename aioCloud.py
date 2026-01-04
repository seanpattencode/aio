#!/usr/bin/env python3
# cloud.py - Google Drive sync via rclone (extracted from aio.py)
import os, subprocess as sp, json, shutil
from pathlib import Path

RCLONE_REMOTE, RCLONE_BACKUP_PATH = 'aio-gdrive', 'aio-backup'
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.expanduser("~/.local/share/aios")
_RCLONE_ERR_FILE = Path(DATA_DIR) / '.rclone_err'

def get_rclone(): return shutil.which('rclone') or next((p for p in ['/usr/bin/rclone', os.path.expanduser('~/.local/bin/rclone')] if os.path.isfile(p)), None)

def configured():
    r = sp.run([get_rclone(), 'listremotes'], capture_output=True, text=True) if get_rclone() else None
    return r and r.returncode == 0 and f'{RCLONE_REMOTE}:' in r.stdout

def account():
    if not (rc := get_rclone()): return None
    try:
        token = json.loads(json.loads(sp.run([rc, 'config', 'dump'], capture_output=True, text=True).stdout).get(RCLONE_REMOTE, {}).get('token', '{}')).get('access_token')
        if not token: return None
        import urllib.request
        u = json.loads(urllib.request.urlopen(urllib.request.Request('https://www.googleapis.com/drive/v3/about?fields=user', headers={'Authorization': f'Bearer {token}'}), timeout=5).read()).get('user', {})
        return f"{u.get('displayName', '')} <{u.get('emailAddress', 'unknown')}>"
    except: return None

def sync_data(wait=False):
    if not (rc := get_rclone()) or not configured(): return False, None
    def _sync():
        r = sp.run([rc, 'sync', str(Path(SCRIPT_DIR) / 'data'), f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}', '-q'], capture_output=True, text=True)
        _RCLONE_ERR_FILE.write_text(r.stderr) if r.returncode != 0 else _RCLONE_ERR_FILE.unlink(missing_ok=True); return r.returncode == 0
    return (True, _sync()) if wait else (__import__('threading').Thread(target=_sync, daemon=True).start(), (True, None))[1]

def pull_notes():
    if not (rc := get_rclone()) or not configured(): return False
    nd, ad = Path(SCRIPT_DIR) / 'data' / 'notebook', Path(SCRIPT_DIR) / 'data' / 'notebook' / 'archive'
    r = sp.run([rc, 'lsf', f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}/notebook/archive'], capture_output=True, text=True)
    cloud_archived = set(r.stdout.strip().split('\n')) if r.returncode == 0 else set()
    for f in nd.glob('*.md'):  # move locally if archived on cloud
        if f.name in cloud_archived: ad.mkdir(exist_ok=True); shutil.move(str(f), str(ad / f.name))
    sp.run([rc, 'copy', f'{RCLONE_REMOTE}:{RCLONE_BACKUP_PATH}/notebook', str(nd), '-u', '-q', '--exclude=archive/**'], capture_output=True); return True

def install_rclone():
    import platform
    bd, arch = os.path.expanduser('~/.local/bin'), 'amd64' if platform.machine() in ('x86_64', 'AMD64') else 'arm64'
    print(f"Installing rclone..."); os.makedirs(bd, exist_ok=True)
    if sp.run(f'curl -sL https://downloads.rclone.org/rclone-current-linux-{arch}.zip -o /tmp/rclone.zip && unzip -qjo /tmp/rclone.zip "*/rclone" -d {bd} && chmod +x {bd}/rclone', shell=True).returncode == 0:
        print(f"✓ Installed"); return f'{bd}/rclone'
    return None

def login():
    rc = get_rclone() or install_rclone()
    if not rc: print("✗ rclone install failed"); return False
    sp.run([rc, 'config', 'create', RCLONE_REMOTE, 'drive'])
    if configured(): print(f"✓ Logged in as {account() or 'unknown'}"); sync_data(wait=True); return True
    print("✗ Login failed - try again"); return False

def logout():
    if configured(): sp.run([get_rclone(), 'config', 'delete', RCLONE_REMOTE]); print("✓ Logged out"); return True
    print("Not logged in"); return False

def status():
    if configured(): print(f"✓ Logged in: {account() or RCLONE_REMOTE}"); return True
    print("✗ Not logged in. Run: aio gdrive login"); return False

if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    {'login': login, 'logout': logout, 'status': status, 'sync': lambda: sync_data(wait=True), 'pull': pull_notes}.get(cmd, status)()
