"""aio remove - Remove project or command"""
import sys
from . _common import init_db, load_proj, load_apps, rm_proj, rm_app, list_all

def run():
    init_db()
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    if not wda: print("Usage: a remove <#|name>\n"); list_all(); sys.exit(0)
    projs, apps = load_proj(), load_apps()
    if wda.isdigit():
        idx = int(wda)
        if idx < len(projs): ok, msg = rm_proj(idx)
        elif idx < len(projs) + len(apps): ok, msg = rm_app(idx - len(projs))
        else: print(f"x Invalid index: {idx}"); list_all(); sys.exit(1)
    else:
        ai = next((i for i, (n, _) in enumerate(apps) if n.lower() == wda.lower()), None)
        if ai is None: print(f"x Not found: {wda}"); list_all(); sys.exit(1)
        ok, msg = rm_app(ai)
    print(f"{'✓' if ok else 'x'} {msg}")
    if ok: list_all()
    sys.exit(0 if ok else 1)
