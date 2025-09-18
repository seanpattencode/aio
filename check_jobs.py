import sqlite3
from datetime import datetime

conn = sqlite3.connect('orchestrator.db')
cursor = conn.execute('''
    SELECT timestamp, level, message
    FROM logs
    WHERE message LIKE '%Job%'
    ORDER BY timestamp DESC
    LIMIT 20
''')

for row in cursor:
    time = datetime.fromtimestamp(row[0]).strftime('%Y-%m-%d %H:%M:%S')
    print(f"{time} [{row[1]}] {row[2]}")

conn.close()