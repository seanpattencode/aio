"""aio config - View/set config"""
import sys
from . _common import init_db, load_cfg, db, list_all

def run():
    init_db()
    cfg = load_cfg()
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    key, val = wda, ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else None
    if not key: [print(f"  {k}: {v[:50]}{'...' if len(v)>50 else ''}") for k, v in sorted(cfg.items())]
    elif val:
        val = '' if val in ('off', 'none', '""', "''") else val
        with db() as c: c.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (key, val)); c.commit()
        list_all(quiet=True)
        print(f"✓ {key}={'(cleared)' if not val else val}")
    else: print(f"{key}: {cfg.get(key, '(not set)')}")
