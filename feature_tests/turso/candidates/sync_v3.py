import socket, subprocess, os, libsql_experimental as l
# 1. Connect to local DB with 'sync_url' to enable Cloud Sync (Embedded Replica)
db = l.connect("local.db", sync_url=os.getenv("TURSO_URL"), auth_token=os.getenv("TURSO_TOKEN"))
db.sync() # Pull: Get latest changes from internet to prevent conflicts
# 2. Run CLI task (date) & save to DB with device name (Atomic Commit)
db.execute("CREATE TABLE IF NOT EXISTS logs (device TEXT, time TEXT)")
db.execute("INSERT INTO logs VALUES (?, ?)", (socket.gethostname(), subprocess.getoutput("date").strip()))
db.commit(); db.sync() # Push: Upload result to the internet
