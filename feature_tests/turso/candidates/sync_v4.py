import os, socket, subprocess, libsql_experimental as l
db = l.connect("local.db", sync_url=os.getenv("TURSO_URL"), auth_token=os.getenv("TURSO_TOKEN"))
db.sync() # Pull latest state to prevent local conflicts
db.execute("CREATE TABLE IF NOT EXISTS runs (dev TEXT, t TEXT)")
# Task: atomic insert of device name + CLI time (race conditions handled by primary)
db.execute("INSERT INTO runs VALUES (?, ?)", (socket.gethostname(), subprocess.getoutput("date")))
db.commit(); db.sync() # Push changes to cloud immediately
