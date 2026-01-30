"""aio login - Token sync (gh + gdrive accounts)"""
import sys, shutil, subprocess as sp
from pathlib import Path
from .sync import sync, SYNC_ROOT
from ._common import cloud_account

LOGIN_DIR = SYNC_ROOT / 'login'
RCLONE_LOCAL = Path.home() / '.config/rclone/rclone.conf'

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
    print(f"gh: {gh_local[:16]}..." if gh_local else "gh: x")

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
        if gh_local: (LOGIN_DIR/'gh_token').write_text(gh_local)
        if RCLONE_LOCAL.exists(): shutil.copy(RCLONE_LOCAL, LOGIN_DIR/'rclone.conf')
        sync('login'); print("✓ saved")
    elif wda == 'apply':
        if (LOGIN_DIR/'gh_token').exists() and not gh_local:
            sp.run(f'echo "{(LOGIN_DIR/"gh_token").read_text().strip()}" | gh auth login --with-token', shell=True)
        if (LOGIN_DIR/'rclone.conf').exists():
            RCLONE_LOCAL.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(LOGIN_DIR/'rclone.conf', RCLONE_LOCAL)
        print("✓ applied")
    elif wda: print(f"save | apply")
