import os, socket, subprocess, libsql_experimental as t
# Connect to local DB and sync with remote Turso instance (pulls latest changes)
db = t.connect("local.db", sync_url=os.getenv("URL"), auth_token=os.getenv("TOKEN")); db.sync()
# Run task (get time via CLI), lock DB locally, and insert data
db.execute("CREATE TABLE IF NOT EXISTS logs (device TEXT, time TEXT)")
db.execute("BEGIN IMMEDIATE") # Prevent local race conditions during transaction
db.execute("INSERT INTO logs VALUES (?, ?)", (socket.gethostname(), subprocess.getoutput("date")))
# Commit changes and sync back to the internet (pushes new row)
db.commit(); db.sync()
print(db.execute("SELECT * FROM logs").fetchall())
