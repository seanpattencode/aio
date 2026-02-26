"""aio gdrive - Cloud sync"""
import sys, os, subprocess as sp
from _common import cloud_login, cloud_logout, cloud_sync, cloud_status, _configured_remotes, RCLONE_BACKUP_PATH, DATA_DIR, SYNC_ROOT, DEVICE_ID, alog
from sync import cloud_sync as cloud_sync_tar

def _pull_auth():
    rem = _configured_remotes(); rem or (print("Login first: aio gdrive login"), exit(1))
    for f, d in [('hosts.yml', '~/.config/gh'), ('rclone.conf', '~/.config/rclone')]:
        os.makedirs(os.path.expanduser(d), exist_ok=True); sp.run(['rclone', 'copy', f'{rem[0]}:{RCLONE_BACKUP_PATH}/backup/auth/{f}', os.path.expanduser(d), '-q'])
    open(f"{DATA_DIR}/.auth_shared","w").close(); os.path.exists(f"{DATA_DIR}/.auth_local") and os.remove(f"{DATA_DIR}/.auth_local"); print("✓ Auth synced (shared)")

HELP = """a gdrive - Google Drive backup (unlimited accounts)

  a gdrive              Status + help
  a gdrive login        Add account (shared rclone key)
  a gdrive login custom Add account (your own client_id, faster)
  a gdrive logout       Remove last account
  a gdrive sync         Backup to GDrive:
                          ~/.local/share/a/ → adata/backup/data/
                          gh+rclone auth → adata/backup/auth/
                          adata/git/ → adata/backup/{device}/git.tar.zst
  a gdrive init         Pull auth from GDrive (new device setup)

  Logs: use 'a log sync' (tar.zst to adata/backup/{device}/)"""

def run():
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    wdb = sys.argv[3] if len(sys.argv) > 3 else None
    if wda == 'login': cloud_login(custom=wdb == 'custom')
    elif wda == 'logout': cloud_logout()
    elif wda == 'sync':
        cloud_sync(wait=True)
        ok, msg = cloud_sync_tar(str(SYNC_ROOT), 'git')
        print(f"✓ Synced data + auth + git ({msg}) to GDrive")
        if ok: alog(f"gdrive sync → gdrive:{RCLONE_BACKUP_PATH}/backup/data/ + auth/ + {DEVICE_ID}/git.tar.zst")
    elif wda == 'init': _pull_auth()
    else: cloud_status(); print(f"\n{HELP}")
run()
