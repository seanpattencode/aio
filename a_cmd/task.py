"""aio task - Task management for agents and humans"""
import sys, os
from . _common import init_db, db

def run():
    init_db()
    wda = sys.argv[2] if len(sys.argv) > 2 else None
