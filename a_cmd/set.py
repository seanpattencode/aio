"""aio set - Settings"""
import sys
from pathlib import Path
from . _common import DATA_DIR

def run():
    f = sys.argv[2] if len(sys.argv) > 2 else None
    p = Path(DATA_DIR) / f if f else None
    v = sys.argv[3] if len(sys.argv) > 3 else None
    if not f:
        s = "on" if (Path(DATA_DIR) / 'n').exists() else "off"
        print(f"1. n [{s}] commands without aio prefix\n   aio set n {'off' if s == 'on' else 'on'}")
        return
    if v == 'on': p.touch(); print(f"✓ on - open new terminal tab")
    elif v == 'off': p.unlink(missing_ok=True); print(f"✓ off - open new terminal tab")
    else: print("on" if p.exists() else "off")
