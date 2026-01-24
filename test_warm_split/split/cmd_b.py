import sqlite3, shutil
def run():
    return f"cmd_b: {sqlite3.sqlite_version} {shutil.which('python3')}"
