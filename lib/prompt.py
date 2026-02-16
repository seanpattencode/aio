"""aio prompt - Manage default prompt"""
import sys
from _common import PROMPTS_DIR, get_prompt, list_all
from sync import sync

def run():
    pf = PROMPTS_DIR / 'default.txt'
    val = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    if not val:
        cur = get_prompt('default') or ''
        print(f"Current: {cur or '(none)'}"); val = input("New (empty to clear): ").strip()
        if val == '' and cur == '': return
    val = '' if val in ('off', 'none', '""', "''") else val
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True); pf.write_text(val); sync()
    list_all(quiet=True); print(f"✓ {'(cleared)' if not val else val}")
