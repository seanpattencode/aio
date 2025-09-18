#!/usr/bin/env python3
import sqlite3
import json
import time

# Connect to the orchestrator database
conn = sqlite3.connect('orchestrator.db')
cursor = conn.cursor()

# Insert a trigger for the llm_processor job
trigger_data = {
    'job_name': 'llm_processor',
    'args': '[]',
    'kwargs': json.dumps({"prompt": "Test LLM processing", "model": "test"}),
    'created': time.time()
}

cursor.execute(
    "INSERT INTO triggers (job_name, args, kwargs, created) VALUES (?, ?, ?, ?)",
    (trigger_data['job_name'], trigger_data['args'], trigger_data['kwargs'], trigger_data['created'])
)

conn.commit()
print(f"Trigger added for {trigger_data['job_name']} with prompt: Test LLM processing")

# Check if the trigger was added
cursor.execute("SELECT * FROM triggers WHERE processed IS NULL")
pending = cursor.fetchall()
print(f"Pending triggers: {len(pending)}")

conn.close()