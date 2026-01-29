"""aio gdrive - Cloud sync"""
import sys, os, subprocess as sp
from . _common import cloud_login, cloud_logout, cloud_sync, cloud_status, _configured_remotes, RCLONE_BACKUP_PATH

def _pull_auth():
    rem = _configured_remotes(); rem or (print("Login first: aio gdrive login"), exit(1))
    for f, d in [('hosts.yml', '~/.config/gh'), ('rclone.conf', '~/.config/rclone')]:
        os.makedirs(os.path.expanduser(d), exist_ok=True); sp.run(['rclone', 'copy', f'{rem[0]}:{RCLONE_BACKUP_PATH}/auth/{f}', os.path.expanduser(d), '-q'])
    print("✓ Auth synced")

def run():
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    if wda == 'login': cloud_login()
    elif wda == 'logout': cloud_logout()
    elif wda == 'sync': cloud_sync(wait=True)
    elif wda == 'init': _pull_auth()  # new device: pull gh token after rclone login
    else: cloud_status()
