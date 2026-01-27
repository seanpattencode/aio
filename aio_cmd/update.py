"""aio update - Update aio"""
import os, subprocess as sp
from . _common import _sg, list_all, SCRIPT_DIR

def run():
    if _sg('rev-parse', '--git-dir').returncode != 0: print("x Not in git repo"); return
    print("Checking..."); before = _sg('rev-parse', 'HEAD').stdout.strip()[:8]
    if not before or _sg('fetch').returncode != 0: return
    if 'behind' not in _sg('status', '-uno').stdout: print(f"✓ Up to date ({before})"); list_all(); return
    changed = _sg('diff', '--name-only', f'{before}..origin/HEAD').stdout
    print("Downloading..."); _sg('pull', '--ff-only')
    after = _sg('rev-parse', 'HEAD').stdout.strip()[:8]; print(f"✓ {before} -> {after}" if after else "✓ Done")
    # Always update shell functions; full install only if deps changed
    sp.run(['bash', f'{SCRIPT_DIR}/install.sh', '--shell'], capture_output=True)
    list_all(); print("Run: source ~/.bashrc or ~/.zshrc")
