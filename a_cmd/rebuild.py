"""aio rebuild - Delete local DB and rebuild from events.jsonl"""
import os, glob
from . _common import DB_PATH, init_db, replay_events
def run(): [os.remove(f) for f in glob.glob(DB_PATH+"*")]; init_db(); replay_events(full=True); print("✓ Rebuilt")
