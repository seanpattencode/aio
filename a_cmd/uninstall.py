"""aio uninstall - Uninstall aio"""
import os, shutil

def run():
    if input("Uninstall aio? (y/n): ").lower() in ['y', 'yes']:
        [os.remove(p) for p in [os.path.expanduser(f"~/.local/bin/{f}") for f in ["aio", "aioUI.py"]] if os.path.exists(p)]
        shutil.rmtree(os.path.expanduser("~/.local/share/aios"), ignore_errors=True)
        print("✓ aio uninstalled")
        os._exit(0)
