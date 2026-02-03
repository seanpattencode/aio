"""aio gdrive - Cloud sync"""
import sys, os, subprocess as sp
from . _common import cloud_login, cloud_logout, cloud_sync, cloud_status, _configured_remotes, RCLONE_BACKUP_PATH, DATA_DIR

def _pull_auth():
    rem = _configured_remotes(); rem or (print("Login first: aio gdrive login"), exit(1))
    for f, d in [('hosts.yml', '~/.config/gh'), ('rclone.conf', '~/.config/rclone')]:
        os.makedirs(os.path.expanduser(d), exist_ok=True); sp.run(['rclone', 'copy', f'{rem[0]}:{RCLONE_BACKUP_PATH}/auth/{f}', os.path.expanduser(d), '-q'])
    open(f"{DATA_DIR}/.auth_shared","w").close(); os.path.exists(f"{DATA_DIR}/.auth_local") and os.remove(f"{DATA_DIR}/.auth_local"); print("✓ Auth synced (shared)")

HELP = """a gdrive - Google Drive backup (2 account slots)

  a gdrive          Status + help
  a gdrive login    Add account (up to 2 for redundancy)
  a gdrive logout   Remove last account
  a gdrive sync     Backup to GDrive:
                      ~/.local/share/a/ → a-backup/
                      gh+rclone auth → a-backup/auth/
  a gdrive init     Pull auth from GDrive (new device setup)

  Logs: use 'a log sync' (tar.zst to a-backup/logs/)"""

def run():
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    if wda == 'login': cloud_login()
    elif wda == 'logout': cloud_logout()
    elif wda == 'sync': cloud_sync(wait=True); print("✓ Synced data + logs + auth to GDrive")
    elif wda == 'init': _pull_auth()
    else: cloud_status(); print(f"\n{HELP}")
