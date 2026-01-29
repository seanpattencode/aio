"""aio move - Reorder projects"""
import sys
from . _common import db, DEVICE_ID, list_all, _refresh_cache

def run():
    args = sys.argv[2:]
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        print("Usage: a move <from> <to>"); sys.exit(1)
    fr, to = int(args[0]), int(args[1])
    with db() as c:
        rows = c.execute("SELECT id FROM projects WHERE device IN (?, '*') ORDER BY display_order", (DEVICE_ID,)).fetchall()
        if fr < 0 or fr >= len(rows) or to < 0 or to >= len(rows):
            print(f"x Invalid index (0-{len(rows)-1})"); sys.exit(1)
        ids = [r[0] for r in rows]
        ids.insert(to, ids.pop(fr))
        for i, pid in enumerate(ids): c.execute("UPDATE projects SET display_order=? WHERE id=?", (i, pid))
        c.commit()
    _refresh_cache(); print(f"✓ Moved {fr} -> {to}"); list_all()
