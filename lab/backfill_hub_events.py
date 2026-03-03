#!/usr/bin/env python3
"""One-time backfill: export existing hub_jobs to events.jsonl for sync"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aio_cmd._common import db, emit_event, DEVICE_ID

jobs = db().execute('SELECT name,schedule,prompt,device,enabled FROM hub_jobs').fetchall()
if not jobs: print('No hub jobs to backfill'); sys.exit(0)
for j in jobs: emit_event('hub', 'add', {'name': j[0], 'schedule': j[1], 'prompt': j[2], 'device': j[3] or DEVICE_ID, 'enabled': j[4]})
print(f'✓ Exported {len(jobs)} hub jobs to events.jsonl - run "aio hub sync" to push')
