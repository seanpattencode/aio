"""aio install - Install aio"""
import os
from _common import SCRIPT_DIR

def run():
    ac = os.path.join(os.path.dirname(SCRIPT_DIR), "a.c")
    os.execvp("bash", ["bash", ac, "install"])
