"""aio done - Signal completion"""
from pathlib import Path
from . _common import DATA_DIR

def run():
    Path(f"{DATA_DIR}/.done").touch()
    print("✓ done")
