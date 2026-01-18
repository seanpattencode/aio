import os, platform, subprocess, libsql_experimental as sql
# Connect to local DB with sync enabled (Embedded Replica)
con = sql.connect("local.db", sync_url=os.getenv("URL"), auth_token=os.getenv("TOKEN"))
con.sync() # Pull latest state to prevent conflicts
con.execute("CREATE TABLE IF NOT EXISTS logs (device TEXT, time TEXT)")
# Run subprocess 'date', capture output, insert atomically
con.execute("INSERT INTO logs VALUES (?, ?)", (platform.node(), subprocess.getoutput("date")))
con.commit(); con.sync() # Save locally then Push to Turso
