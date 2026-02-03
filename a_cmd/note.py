# Append-only notes: {id}_{timestamp}.txt = no conflicts
# Uses sync.py append-only logic for conflict-free sync

import sys, subprocess as sp
from pathlib import Path
from datetime import datetime
from ._common import DEVICE_ID, SYNC_ROOT
from .sync import _sync, ts, add_timestamps

NOTES_DIR = SYNC_ROOT / 'notes'

def _save(text, status='pending', project=None, due=None, device=None):
    """Save a new note with timestamp"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    # Create filename: first 8 chars of content hash + timestamp
    slug = hex(hash(text) & 0xffffffff)[2:].zfill(8)
    filename = f'{slug}_{ts()}.txt'
    content = f"Text: {text}\nStatus: {status}\nDevice: {device or DEVICE_ID}\nCreated: {datetime.now():%Y-%m-%d %H:%M}\n"
    if project:
        content += f"Project: {project}\n"
    if due:
        content += f"Due: {due}\n"
    (NOTES_DIR / filename).write_text(content)
    _sync(silent=True)
    return filename

def _load():
    """Load all notes, sorted by timestamp (newest first)"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    _sync(silent=True)
    notes = []
    for f in sorted(NOTES_DIR.glob('*.txt'), key=lambda p: p.stem.rsplit('_', 1)[-1] if '_20' in p.stem else '0', reverse=True):
        if f.name.startswith('.'):
            continue
        d = {k.strip(): v.strip() for line in f.read_text().splitlines() if ':' in line for k, v in [line.split(':', 1)]}
        if 'Text' in d:
            notes.append((f.stem, d['Text'], d.get('Due'), d.get('Project'), d.get('Device', DEVICE_ID), d.get('Status', 'pending'), d.get('Created'), f))
    return notes

def _update(old_file, text, status='pending', project=None, due=None, device=None):
    """Update note by archiving old and creating new version"""
    # Archive old version
    archive = NOTES_DIR / '.archive'
    archive.mkdir(exist_ok=True)
    if old_file.exists():
        old_file.rename(archive / old_file.name)
    # Save new version
    return _save(text, status, project, due, device)

def _rm(filepath):
    """Delete a note (move to archive)"""
    archive = NOTES_DIR / '.archive'
    archive.mkdir(exist_ok=True)
    if filepath.exists():
        filepath.rename(archive / filepath.name)
    _sync(silent=True)

def run():
    raw = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    notes = _load()
    pending = [n for n in notes if n[5] == 'pending']

    # Quick add
    if raw and raw[0] != '?':
        _save(raw)
        print("✓")
        return

    # Search filter
    if raw:
        pending = [n for n in pending if raw[1:].lower() in n[1].lower()]

    if not pending:
        print("a n <text>")
        return

    # Non-interactive mode
    if not sys.stdin.isatty():
        for nid, t, _, p, _, _, _, _ in pending[:10]:
            print(f"{t}" + (f" @{p}" if p else ""))
        return

    # Interactive mode
    url = sp.run(['git', '-C', str(SYNC_ROOT), 'remote', 'get-url', 'origin'], capture_output=True, text=True).stdout.strip()
    print(f"Notes: {len(pending)} pending\n  {NOTES_DIR}\n  {url}\n")
    print(f"{len(pending)} notes | [a]ck [e]dit [s]earch [q]uit | 1/20=due")
    i = 0
    while i < len(pending):
        nid, txt, due, proj, dev, _, _, filepath = pending[i]
        print(f"\n[{i+1}/{len(pending)}] {txt}" + (f" @{proj}" if proj else "") + (f" [{due}]" if due else "") + (f" <{dev[:8]}>" if dev else ""))
        ch = input("> ").strip()
        if ch == 'a':
            _update(filepath, txt, 'done', proj, due, dev)
            print("✓")
            pending.pop(i)
            continue
        elif ch == 'e':
            nv = input("new: ").strip()
            if nv:
                _update(filepath, nv, 'pending', proj, due, dev)
                print("✓")
            pending = [n for n in _load() if n[5] == 'pending']
            continue
        elif '/' in ch:
            from dateutil.parser import parse
            d = str(parse(ch, dayfirst=False))[:10]
            _update(filepath, txt, 'pending', proj, d, dev)
            print(f"✓ {d}")
            pending = [n for n in _load() if n[5] == 'pending']
            continue
        elif ch == 's':
            q = input("search: ")
            pending = [n for n in _load() if n[5] == 'pending' and q.lower() in n[1].lower()]
            i = 0
            print(f"{len(pending)} results")
            continue
        elif ch == 'q':
            return
        elif ch:
            _save(ch)
            pending = [n for n in _load() if n[5] == 'pending']
            print(f"✓ [{len(pending)}]")
            continue
        i += 1
