"""aio backup - Backup sync status"""
import sys, os, subprocess as sp, shutil, time
from . _common import init_db, DATA_DIR, _die, cloud_configured, cloud_account, RCLONE_BACKUP_PATH

def _ago(ts): d=int(time.time()-ts); return f"{d//86400}d" if d>=86400 else f"{d//3600}h" if d>=3600 else f"{d//60}m" if d>=60 else f"{d}s"

def run():
    init_db(); wda = sys.argv[2] if len(sys.argv) > 2 else None
    if wda == 'setup':
        url = sys.argv[3] if len(sys.argv) > 3 else (sp.run(['gh', 'repo', 'view', 'aio-sync', '--json', 'url', '-q', '.url'], capture_output=True, text=True).stdout.strip() or sp.run(['gh', 'repo', 'create', 'aio-sync', '--private', '-y'], capture_output=True, text=True).stdout.strip()) if shutil.which('gh') else None
        if not url: _die("x No URL (need gh CLI or provide URL)")
        sp.run(f'cd "{DATA_DIR}" && git init -q 2>/dev/null; git remote set-url origin {url} 2>/dev/null || git remote add origin {url}; git fetch origin 2>/dev/null && git reset --hard origin/main 2>/dev/null || (git add -A && git commit -m "init" -q && git push -u origin main)', shell=True); print("✓ Sync ready"); return
    ef, gf = f"{DATA_DIR}/events.jsonl", f"{DATA_DIR}/.gdrive_sync"
    gu = sp.run(f'cd "{DATA_DIR}" && git remote get-url origin 2>/dev/null', shell=True, capture_output=True, text=True).stdout.strip()
    gt = sp.run(f'cd "{DATA_DIR}" && git log -1 --format=%ct 2>/dev/null', shell=True, capture_output=True, text=True).stdout.strip()
    print(f"Local:  {'✓ '+ef+' ('+_ago(os.path.getmtime(ef))+' ago)' if os.path.exists(ef) else 'x'}")
    print(f"Git:    {'✓ '+gu+' ('+_ago(int(gt))+')' if gu and gt else 'x (aio backup setup)'}")
    if cloud_configured(): print(f"GDrive: ✓ {cloud_account() or '?'} /{RCLONE_BACKUP_PATH}" + (f" ({_ago(os.path.getmtime(gf))} ago)" if os.path.exists(gf) else " (never synced)"))
    else: print("GDrive: x (aio gdrive login)")
