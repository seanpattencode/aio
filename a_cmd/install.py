"""aio install - Install aio"""
import os
from . _common import SCRIPT_DIR

def run():
    script = os.path.join(SCRIPT_DIR, "install.sh")
    if os.path.exists(script):
        os.execvp("bash", ["bash", script])
    else:
        url = "https://raw.githubusercontent.com/seanpattencode/aio/main/install.sh"
        os.execvp("bash", ["bash", "-c", f"curl -fsSL {url} | bash"])
