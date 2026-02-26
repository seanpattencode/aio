"""aio login - Token sync (gh + gdrive accounts)"""
import sys, shutil, subprocess as sp
from pathlib import Path
from datetime import datetime
from sync import sync, SYNC_ROOT
from _common import cloud_account, DEVICE_ID

LOGIN_DIR = SYNC_ROOT / 'login'
RCLONE_LOCAL = Path.home() / '.config/rclone/rclone.conf'

def _save_gh(token):
    (LOGIN_DIR/f'gh_{DEVICE_ID}.txt').write_text(f"Token: {token}\nDevice: {DEVICE_ID}\nCreated: {datetime.now():%Y-%m-%d %H:%M}\n")

def _load_gh():
    # Try own device first, then others sorted by date
    files = sorted(LOGIN_DIR.glob('gh_*.txt'), key=lambda f: f.stat().st_mtime, reverse=True)
    own = [f for f in files if DEVICE_ID in f.name]
    for f in (own + [x for x in files if x not in own]):
        for line in f.read_text().splitlines():
            if line.startswith('Token:'): return line.split(':', 1)[1].strip(), f.stem
    return None, None

def _rclone_remotes():
    import re
    if not RCLONE_LOCAL.exists(): return []
    return [m.group(1) for m in re.finditer(r'^\[([^\]]+)\]', RCLONE_LOCAL.read_text(), re.M)]

def run():
    LOGIN_DIR.mkdir(parents=True, exist_ok=True)
    (LOGIN_DIR/'.git').exists() or sync('login')
    url = sp.run(['git','-C',str(LOGIN_DIR),'remote','get-url','origin'], capture_output=True, text=True).stdout.strip()
    print(f"Login: {LOGIN_DIR}\n  {url}\n")

    # gh token
    gh_local = sp.run(['gh','auth','token'], capture_output=True, text=True).stdout.strip()
    gh_sync, gh_src = _load_gh()
    print(f"gh: {gh_local[:16]}..." if gh_local else "gh: x")
    if gh_sync: print(f"  sync: {gh_src}")

    # rclone/gdrive
    remotes = _rclone_remotes()
    print(f"rclone:")
    for rem in remotes:
        print(f"  {rem}: {cloud_account(rem)}")
    if not remotes: print("  x none")

    # list synced files
    files = [f.name for f in LOGIN_DIR.glob('*') if f.is_file()]
    print(f"\nSynced: {', '.join(files) if files else '(none)'}")

    wda = sys.argv[2] if len(sys.argv) > 2 else None
    if wda == 'save':
        if gh_local: _save_gh(gh_local)
        if RCLONE_LOCAL.exists(): shutil.copy(RCLONE_LOCAL, LOGIN_DIR/'rclone.conf')
        sync('login'); print("✓ saved")
    elif wda == 'apply':
        if gh_sync and not gh_local:
            sp.run(f'echo "{gh_sync}" | gh auth login --with-token', shell=True)
            print(f"✓ gh from {gh_src}")
        if (LOGIN_DIR/'rclone.conf').exists():
            RCLONE_LOCAL.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(LOGIN_DIR/'rclone.conf', RCLONE_LOCAL)
            print("✓ rclone applied")
    elif wda: print(f"save | apply")
run()
