"""aio backup - Folder sync status (~/gdrive/a = source of truth)"""
import sys, os, subprocess as sp, time, json
from pathlib import Path
from .sync import SYNC_DIR, NOTES, DB, pull, push, _git
from ._common import LOG_DIR, cloud_sync, cloud_account, _configured_remotes, RCLONE_BACKUP_PATH, DATA_DIR, get_rclone

def _ago(ts): d=int(time.time()-ts); return f"{d//86400}d" if d>=86400 else f"{d//3600}h" if d>=3600 else f"{d//60}m" if d>=60 else f"{d}s"
_sz = lambda b: f"{b/1024/1024:.1f}MB" if b>=1024*1024 else f"{b/1024:.0f}KB" if b>=1024 else f"{b}B"
def _folder_url(rem):
    try: return f"https://drive.google.com/drive/folders/{next(f['ID'] for f in json.loads(sp.run([get_rclone(),'lsjson',f'{rem}:','--dirs-only'],capture_output=True,text=True).stdout) if f['Name']==RCLONE_BACKUP_PATH)}"
    except: return None

def run():
    notes_n = len(list(NOTES.glob('*.md'))); acks_n = len(list(NOTES.glob('*.ack')))
    db_sz = DB.stat().st_size if DB.exists() else 0
    log_sz = sum(f.stat().st_size for f in Path(LOG_DIR).glob('*.log')) if os.path.isdir(LOG_DIR) else 0
    log_n = len(list(Path(LOG_DIR).glob('*.log'))) if os.path.isdir(LOG_DIR) else 0

    print("DATA (~/gdrive/a = source of truth)")
    print(f"  notes/     {notes_n:>5} files  → {notes_n - acks_n} active, {acks_n} done")
    print(f"  aio.db     {_sz(db_sz):>8}  → local cache")
    print(f"  logs/      {_sz(log_sz):>8}  → {log_n} session logs")

    print(f"\nSYNC")
    # Git sync (folder → github)
    gu = _git('remote','get-url','origin').stdout.strip()
    if gu:
        sys.stdout.write("  Git: syncing...\r"); sys.stdout.flush(); push('backup'); sys.stdout.write("\033[2K\r")
        gt = _git('log','-1','--format=%ct').stdout.strip()
        print(f"  Git:    ✓ {gu}" + (f" ({_ago(int(gt))} ago)" if gt.isdigit() else ""))
    else: print("  Git:    x (not configured)")

    # GDrive (folder auto-syncs, just sync logs)
    remotes = _configured_remotes()
    if remotes:
        gf = f"{DATA_DIR}/.gdrive_sync"
        sys.stdout.write("  GDrive: syncing logs...\r"); sys.stdout.flush(); cloud_sync(wait=True); sys.stdout.write("\033[2K\r"); Path(gf).touch()
        for rem in remotes: print(f"  GDrive: ✓ {rem} {cloud_account(rem)} ({_ago(os.path.getmtime(gf))} ago)"); url = _folder_url(rem); url and print(f"          {url}")
    else: print("  GDrive: ✓ (folder auto-syncs)")
