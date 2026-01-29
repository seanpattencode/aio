"""aio prompt - Manage default prompt"""
import sys
from . _common import init_db, load_cfg, db, list_all

def run():
    init_db()
    cfg = load_cfg()
    val = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    if not val:
        cur = cfg.get('default_prompt', '')
        print(f"Current: {cur or '(none)'}"); val = input("New (empty to clear): ").strip()
        if val == '' and cur == '': return
    val = '' if val in ('off', 'none', '""', "''") else val
    with db() as c: c.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", ('default_prompt', val)); c.commit()
    list_all(quiet=True)
    print(f"✓ {'(cleared)' if not val else val}")
