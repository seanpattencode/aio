"""aio log [#|tail #|clean days|grab|archive] - View agent logs"""
import sys, os, time, subprocess as sp, shutil
from pathlib import Path
from datetime import datetime
from . _common import init_db, LOG_DIR, DEVICE_ID
from .sync import sync

CLAUDE_DIR = Path.home()/'.claude'
SIZE_THRESH = 10 * 1024 * 1024  # 10MB - larger files go to gdrive
GDRIVES = {'aio-gdrive:': 'seanpattencode', 'aio-gdrive2:': 'spatten760'}
GDRIVE_PATH = 'aio-backup/logs'

def _grab():
    """Copy Claude logs to sync dir"""
    dst = Path(LOG_DIR)/'claude'/DEVICE_ID; dst.mkdir(parents=True, exist_ok=True)
    n = 0
    if (h := CLAUDE_DIR/'history.jsonl').exists(): shutil.copy2(h, dst/'history.jsonl'); n += 1
    for f in CLAUDE_DIR.glob('projects/**/*.jsonl'):
        rel = f.relative_to(CLAUDE_DIR/'projects'); (dst/'projects'/rel.parent).mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst/'projects'/rel); n += 1
    _archive(); sync('logs'); print(f"✓ {n} files → {dst}")

def _archive():
    """Move large files to gdrive, keep small in git"""
    large = Path(LOG_DIR)/'_large'; large.mkdir(exist_ok=True)
    moved = []
    for f in Path(LOG_DIR).rglob('*'):
        if f.is_file() and f.stat().st_size > SIZE_THRESH and '_large' not in str(f):
            dst = large/f.name; shutil.move(f, dst); moved.append(dst)
    if moved:
        for gd in GDRIVES.keys(): sp.run(['rclone', 'copy', str(large), f'{gd}{GDRIVE_PATH}/_large', '-q'])
        print(f"  → {len(moved)} large files to gdrive")
    _write_readme()

def _write_readme():
    (Path(LOG_DIR)/'README.md').write_text(f"""# Agent Logs
Small files (<10MB) synced here via git. Large files stored on gdrive with dual backup.

## Retrieve large files
```bash
rclone copy aio-gdrive:{GDRIVE_PATH}/_large ./
```

## Structure
- `*.log` - tmux raw session output
- `claude/` - Claude Code conversation logs (.jsonl)
- `_large/` - local cache of large files (not in git)

Last updated: {datetime.now():%Y-%m-%d %H:%M}
""")

def run():
    init_db(); Path(LOG_DIR).mkdir(parents=True, exist_ok=True); sync('logs')
    sel = sys.argv[2] if len(sys.argv) > 2 else None
    if sel == 'grab': _grab(); return
    if sel == 'archive': _archive(); sync('logs'); print("✓ archived"); return
    logs = sorted(Path(LOG_DIR).glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
    if not logs: print("No logs"); return
    if sel == 'clean': days = int(sys.argv[3]) if len(sys.argv) > 3 else 7; old = [f for f in logs if (time.time() - f.stat().st_mtime) > days*86400]; [f.unlink() for f in old]; print(f"✓ {len(old)} logs"); return
    if sel == 'tail': f = logs[int(sys.argv[3])] if len(sys.argv) > 3 and sys.argv[3].isdigit() else logs[0]; os.execvp('tail', ['tail', '-f', str(f)])
    if sel and sel.isdigit() and (i := int(sel)) < len(logs): sp.run(['tmux', 'new-window', f'cat "{logs[i]}"; read']); return
    total = sum(f.stat().st_size for f in logs); url = sp.run(['git','-C',LOG_DIR,'remote','get-url','origin'], capture_output=True, text=True).stdout.strip()
    print(f"Logs: {len(logs)}, {total/1024/1024:.1f}MB\n  Git:   {url}")
    for gd, acct in GDRIVES.items():
        r = sp.run(['rclone', 'lsl', f'{gd}{GDRIVE_PATH}/_large', '--max-depth', '1'], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            lines = r.stdout.strip().split('\n'); n = len(lines)
            latest = max(l.split()[1] + ' ' + l.split()[2][:5] for l in lines if len(l.split()) >= 3)
            print(f"  gdrive ({acct}): {n} files, last {latest}")
        else: print(f"  gdrive ({acct}): ✗")
    for name, base, files in [('Claude', Path.home()/'.claude', ['history.jsonl','projects']), ('Codex', Path.home()/'.codex', ['history.jsonl','sessions']), ('Gemini', Path.home()/'.gemini', ['settings.json']), ('Aider', Path.home()/'.aider', ['caches'])]:
        if base.exists(): parts = [f"{f}({(base/f).stat().st_size//1024}KB)" if (base/f).is_file() else f"{f}({len(list((base/f).iterdir()))})" for f in files if (base/f).exists()]; parts and print(f"  {name}: {base} [{', '.join(parts)}]")
    for i, f in enumerate(logs[:20]):
        sz, nm, mt = f.stat().st_size/1024, f.stem, f.stat().st_mtime; parts = nm.split('__'); dev, sn = (parts[0][:10], '__'.join(parts[1:])) if len(parts) > 1 else ('-', nm)
        print(f"  {i}  {datetime.fromtimestamp(mt).strftime('%m/%d %H:%M')}  {dev:<10} {sn:<25} {sz:>5.0f}KB  {f}")
    print("\nSelect:\n  a log 0")
