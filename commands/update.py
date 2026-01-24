"""aio update - update aio itself"""
import subprocess as sp, os

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _sg(*a, **k):
    return sp.run(['git', '-C', SCRIPT_DIR] + list(a), capture_output=True, text=True, **k)

def run(args):
    if _sg('rev-parse', '--git-dir').returncode != 0:
        print("x Not in git repo"); return
    print("Checking...")
    before = _sg('rev-parse', 'HEAD').stdout.strip()[:8]
    if not before or _sg('fetch').returncode != 0:
        return
    if 'behind' not in _sg('status', '-uno').stdout:
        print(f"✓ Up to date ({before})")
        return
    print("Downloading...")
    _sg('pull', '--ff-only')
    after = _sg('rev-parse', 'HEAD')
    print(f"✓ {before} -> {after.stdout.strip()[:8]}" if after.returncode == 0 else "✓ Done")
    print("Run: source ~/.bashrc")
