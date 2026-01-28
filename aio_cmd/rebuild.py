"""aio rebuild - Delete local DB and rebuild from events.jsonl"""
import os
from . _common import DB_PATH, init_db, replay_events
def run(): os.remove(DB_PATH) if os.path.exists(DB_PATH) else None; init_db(); replay_events(full=True); print("✓ Rebuilt")
