"""aio backup - Backup sync status"""
import sys, os, subprocess as sp, shutil, time, json
from pathlib import Path
from . _common import init_db, DATA_DIR, LOG_DIR, EVENTS_PATH, DB_PATH, _die, cloud_configured, cloud_account, RCLONE_BACKUP_PATH, RCLONE_REMOTES, get_rclone, _configured_remotes

def _ago(ts): d=int(time.time()-ts); return f"{d//86400}d" if d>=86400 else f"{d//3600}h" if d>=3600 else f"{d//60}m" if d>=60 else f"{d}s"
def _sz(b): return f"{b/1024/1024:.1f}MB" if b>=1024*1024 else f"{b/1024:.0f}KB" if b>=1024 else f"{b}B"
def _gdrive_url(remote):
    try: return f"https://drive.google.com/drive/folders/{next(f['ID'] for f in json.loads(sp.run(['rclone','lsjson',f'{remote}:','--dirs-only'],capture_output=True,text=True).stdout) if f['Name']==RCLONE_BACKUP_PATH)}"
    except: return None

def run():
    init_db(); wda = sys.argv[2] if len(sys.argv) > 2 else None
    if wda == 'setup':
        url = sys.argv[3] if len(sys.argv) > 3 else (sp.run(['gh', 'repo', 'view', 'aio-sync', '--json', 'url', '-q', '.url'], capture_output=True, text=True).stdout.strip() or sp.run(['gh', 'repo', 'create', 'aio-sync', '--private', '-y'], capture_output=True, text=True).stdout.strip()) if shutil.which('gh') else None
        if not url: _die("x No URL (need gh CLI or provide URL)")
        sp.run(f'cd "{DATA_DIR}" && git init -q 2>/dev/null; git remote set-url origin {url} 2>/dev/null || git remote add origin {url}; git fetch origin 2>/dev/null && git reset --hard origin/main 2>/dev/null || (git add -A && git commit -m "init" -q && git push -u origin main)', shell=True); print("✓ Sync ready"); return
    gf = f"{DATA_DIR}/.gdrive_sync"
    gu = sp.run(f'cd "{DATA_DIR}" && git remote get-url origin 2>/dev/null', shell=True, capture_output=True, text=True).stdout.strip()
    gt = sp.run(f'cd "{DATA_DIR}" && git log -1 --format=%ct 2>/dev/null', shell=True, capture_output=True, text=True).stdout.strip()
    # Local data sizes
    ev_sz = os.path.getsize(EVENTS_PATH) if os.path.exists(EVENTS_PATH) else 0
    db_sz = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    log_sz = sum(f.stat().st_size for f in Path(LOG_DIR).glob('*.log')) if os.path.isdir(LOG_DIR) else 0
    log_n = len(list(Path(LOG_DIR).glob('*.log'))) if os.path.isdir(LOG_DIR) else 0
    print("DATA")
    print(f"  events.jsonl  {_sz(ev_sz):>8}  → notes, hub, projects (git)")
    print(f"  aio.db        {_sz(db_sz):>8}  → local cache (rebuilt from events)")
    print(f"  logs/         {_sz(log_sz):>8}  → session logs (gdrive, {log_n} files)")
    # Git sync (events.jsonl = notes/hub/projects)
    print(f"\nSYNC")
    from . _common import db_sync, cloud_sync
    if gu:
        sys.stdout.write("  Git: syncing events...\r"); sys.stdout.flush(); db_sync(); sys.stdout.write("\033[2K\r")
        gt = sp.run(f'cd "{DATA_DIR}" && git log -1 --format=%ct 2>/dev/null', shell=True, capture_output=True, text=True).stdout.strip()
        print(f"  Git:    ✓ {gu} ({_ago(int(gt))} ago)")
    else: print(f"  Git:    x (run: a backup setup)")
    # GDrive sync (logs + events backup)
    remotes = _configured_remotes()
    if remotes:
        sys.stdout.write("  GDrive: syncing logs...\r"); sys.stdout.flush(); cloud_sync(wait=True); sys.stdout.write("\033[2K\r"); Path(gf).touch()
        auth = "local" if os.path.exists(f"{DATA_DIR}/.auth_local") else "shared" if os.path.exists(f"{DATA_DIR}/.auth_shared") else "?"
        sync_ago = f" ({_ago(os.path.getmtime(gf))} ago)" if os.path.exists(gf) else ""
        for rem in remotes: print(f"  GDrive: ✓ {rem} {cloud_account(rem)} ({auth}){sync_ago}"); url = _gdrive_url(rem); url and print(f"          {url}")
    else: print(f"  GDrive: x (run: a gdrive login)")
