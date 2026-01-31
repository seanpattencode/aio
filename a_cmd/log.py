"""aio log [#|tail|clean|grab|sync]"""
import sys, os, time, subprocess as sp, shutil, json
from pathlib import Path
from datetime import datetime
from ._common import init_db, LOG_DIR, DEVICE_ID, RCLONE_REMOTES, RCLONE_BACKUP_PATH, get_rclone
from .sync import cloud_sync
CD = Path.home()/'.claude'

def run():
    init_db(); Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    s = sys.argv[2] if len(sys.argv) > 2 else None
    if s == 'grab':
        dst = Path(LOG_DIR)/'claude'/DEVICE_ID; dst.mkdir(parents=True, exist_ok=True); n = 0
        if (h := CD/'history.jsonl').exists(): shutil.copy2(h, dst/'history.jsonl'); n += 1
        for f in CD.glob('projects/**/*.jsonl'): rel = f.relative_to(CD/'projects'); (dst/'projects'/rel.parent).mkdir(parents=True, exist_ok=True); shutil.copy2(f, dst/'projects'/rel); n += 1
        ok, msg = cloud_sync(LOG_DIR, 'logs'); print(f"{'✓' if ok else 'x'} {n} files {msg}"); return
    if s == 'sync': ok, msg = cloud_sync(LOG_DIR, 'logs'); print(f"{'✓' if ok else 'x'} {msg}"); return
    logs = sorted(Path(LOG_DIR).glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
    if s == 'clean': days = int(sys.argv[3]) if len(sys.argv) > 3 else 7; [f.unlink() for f in logs if (time.time() - f.stat().st_mtime) > days*86400]; print(f"✓ cleaned"); return
    if s == 'tail': f = logs[int(sys.argv[3])] if len(sys.argv) > 3 and sys.argv[3].isdigit() else (logs[0] if logs else None); f and os.execvp('tail', ['tail', '-f', str(f)]); return
    if s and s.isdigit() and logs and (i := int(s)) < len(logs): sp.run(['tmux', 'new-window', f'cat "{logs[i]}"; read']); return
    print(f"Local: {len(logs)} logs, {sum(f.stat().st_size for f in logs)//1024//1024}MB")
    if rc := get_rclone():
        for r in RCLONE_REMOTES:
            try:
                res = sp.run([rc,'lsjson',f'{r}:{RCLONE_BACKUP_PATH}/logs'], capture_output=True, text=True, timeout=15)
                t = {f['Name']:f for f in json.loads(res.stdout)}.get(f'{DEVICE_ID}.tar.zst') if res.returncode==0 else None
                print(f"  {r}: {t['Size']//1024//1024}MB synced {t['ModTime'][:16].replace('T',' ')}\n    https://drive.google.com/file/d/{t['ID']}") if t else print(f"  {r}: x")
            except: print(f"  {r}: timeout")
    for i, f in enumerate(logs[:12]):
        sn = '__'.join(f.stem.split('__')[1:]) or f.stem
        print(f"{i:>2} {datetime.fromtimestamp(f.stat().st_mtime):%m/%d %H:%M} {sn[:26]:<26} {f.stat().st_size//1024:>5}K")
    logs and print("\na log #  view | a log sync")
