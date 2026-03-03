#!/usr/bin/env python3
"""Migrate old flat logs/ to device subfolders, backup old remote logs"""
import subprocess as sp, os, json

REMOTE = 'aio-gdrive'
PATH = 'aio-backup'

def run():
    # 1. Backup old flat logs from remote
    print("1. Checking remote logs structure...")
    r = sp.run(['rclone', 'lsjson', f'{REMOTE}:{PATH}/logs/', '--dirs-only'], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"   No logs/ found or error: {r.stderr.strip()}")
        return

    dirs = json.loads(r.stdout) if r.stdout.strip() else []
    dir_names = [d['Name'] for d in dirs]
    print(f"   Found subfolders: {dir_names}")

    # Check for flat files (old structure)
    r2 = sp.run(['rclone', 'lsjson', f'{REMOTE}:{PATH}/logs/', '--files-only'], capture_output=True, text=True)
    flat_files = json.loads(r2.stdout) if r2.returncode == 0 and r2.stdout.strip() else []

    if flat_files:
        print(f"2. Found {len(flat_files)} flat files (old structure)")
        print("   Backing up to logs/_old/...")
        sp.run(['rclone', 'copy', f'{REMOTE}:{PATH}/logs/', f'{REMOTE}:{PATH}/logs/_old/',
                '--exclude', '*/', '-v'], capture_output=False)
        print("   Removing flat files from logs/...")
        for f in flat_files:
            sp.run(['rclone', 'deletefile', f'{REMOTE}:{PATH}/logs/{f["Name"]}', '-v'], capture_output=False)
        print("   Done migrating remote")
    else:
        print("2. No flat files found - already migrated or empty")

    # 3. Show current state
    print("\n3. Current remote structure:")
    sp.run(['rclone', 'tree', f'{REMOTE}:{PATH}/logs/', '--max-depth', '1'], capture_output=False)

if __name__ == '__main__':
    run()
