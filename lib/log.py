"""aio log [#|tail|clean|grab|sync] - Large files (>100MB) should use cloud storage, not git"""
import sys, os, time, subprocess as sp, shutil, json
from pathlib import Path
from datetime import datetime as D
from _common import init_db, LOG_DIR, DEVICE_ID, RCLONE_BACKUP_PATH, get_rclone, _configured_remotes as CR, cloud_install as CI, alog
from sync import cloud_sync,_merge_rclone as MR
CD = Path.home()/'.claude'

def run():
    init_db(); Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    s = sys.argv[2] if len(sys.argv) > 2 else None
    if s == 'grab':
        dst = Path(LOG_DIR)/'claude'/DEVICE_ID; dst.mkdir(parents=True, exist_ok=True); n = 0
        if (h := CD/'history.jsonl').exists(): shutil.copy2(h, dst/'history.jsonl'); n += 1
        for f in CD.glob('projects/**/*.jsonl'): rel = f.relative_to(CD/'projects'); (dst/'projects'/rel.parent).mkdir(parents=True, exist_ok=True); shutil.copy2(f, dst/'projects'/rel); n += 1
        ok, msg = cloud_sync(LOG_DIR, 'logs'); print(f"{'✓' if ok else 'x'} {n} files {msg}")
        if ok: alog(f"log grab+sync → gdrive:{RCLONE_BACKUP_PATH}/backup/{DEVICE_ID}/logs.tar.zst ({n} claude files)")
        return
    if s == 'sync':
        ok, msg = cloud_sync(LOG_DIR, 'logs'); print(f"{'✓' if ok else 'x'} {msg}")
        if ok: alog(f"log sync → gdrive:{RCLONE_BACKUP_PATH}/backup/{DEVICE_ID}/logs.tar.zst")
        return
    logs = sorted(Path(LOG_DIR).glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
    if s == 'clean': days = int(sys.argv[3]) if len(sys.argv) > 3 else 7; [f.unlink() for f in logs if (time.time() - f.stat().st_mtime) > days*86400]; print(f"✓ cleaned"); return
    if s == 'tail': f = logs[int(sys.argv[3])] if len(sys.argv) > 3 and sys.argv[3].isdigit() else (logs[0] if logs else None); f and os.execvp('tail', ['tail', '-f', str(f)]); return
    if s and s.isdigit() and logs and (i := int(s)) < len(logs): sp.run(['tmux', 'new-window', f'cat "{logs[i]}"; read']); return
    rc = get_rclone() or CI(); MR(); C = rc and CR()
    C or print("gdrive: no login"if rc else"gdrive: no rclone")
    for r in C or []:
        try: t = {x['Name']:x for x in json.loads(sp.run([rc,'lsjson',f'{r}:{RCLONE_BACKUP_PATH}/backup/{DEVICE_ID}'],capture_output=True,text=True,timeout=15).stdout)}.get('logs.tar.zst'); print(f"{r}: {t['Size']//1024//1024}MB @ {D.fromisoformat(t['ModTime'][:19]+'Z').astimezone():%m-%d %H:%M} drive.google.com/file/d/{t['ID']}"if t else f"{r}: ✓ no sync")
        except: print(f"{r}: timeout")
    print(f"\nLocal: {len(logs)} logs, {sum(f.stat().st_size for f in logs)//1024//1024}MB")
    for i, f in enumerate(logs[:12]):
        sn = '__'.join(f.stem.split('__')[1:]) or f.stem
        print(f"{i:>2} {D.fromtimestamp(f.stat().st_mtime):%m/%d %H:%M} {sn[:26]:<26} {f.stat().st_size//1024:>5}K")
    logs and print("\na log #  view | a log sync")
run()
