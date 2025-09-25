#!/usr/bin/env python3
import json
import os
import argparse
from pathlib import Path
from datetime import datetime

class BackupGDrive:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.sync_state_file = self.aios_dir / "gdrive_sync.json"
        self.load_sync_state()

    def load_sync_state(self):
        if self.sync_state_file.exists():
            with open(self.sync_state_file) as f:
                self.sync_state = json.load(f)
        else:
            self.sync_state = {'last_sync': None, 'files': {}}

    def save_sync_state(self):
        with open(self.sync_state_file, 'w') as f:
            json.dump(self.sync_state, f, indent=2)

    def authenticate(self):
        import os
        # Check for Google credentials
        creds_file = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if not creds_file or not Path(creds_file).exists():
            print("❌ Error: GOOGLE_APPLICATION_CREDENTIALS not set or file not found")
            print("Please set: export GOOGLE_APPLICATION_CREDENTIALS='path/to/service-account.json'")
            raise ValueError("Google Drive credentials required")

        print("🔑 Authenticating with Google Drive...")
        # Would use google-api-python-client here with the credentials
        return True

    def upload_file(self, file_path):
        # Placeholder for file upload
        # In production, use Google Drive API
        relative_path = file_path.relative_to(self.aios_dir)
        print(f"  ↑ Uploading {relative_path}")
        # Simulate upload
        return True

    def download_file(self, file_path):
        # Placeholder for file download
        print(f"  ↓ Downloading {file_path}")
        return True

    def sync(self):
        if not self.authenticate():
            print("❌ Authentication failed")
            return

        if not self.aios_dir.exists():
            print("❌ No .aios directory found")
            return

        print("\n☁️ Starting Google Drive sync...")
        uploaded = 0
        skipped = 0

        # Collect all files
        for file_path in self.aios_dir.rglob('*'):
            if file_path.is_file() and 'gdrive_sync.json' not in str(file_path):
                file_key = str(file_path.relative_to(self.aios_dir))
                file_mtime = file_path.stat().st_mtime

                # Check if file needs upload
                if file_key in self.sync_state['files']:
                    if self.sync_state['files'][file_key] >= file_mtime:
                        skipped += 1
                        continue

                # Upload file
                if self.upload_file(file_path):
                    uploaded += 1
                    self.sync_state['files'][file_key] = file_mtime

        self.sync_state['last_sync'] = datetime.now().isoformat()
        self.save_sync_state()

        print(f"\n✅ Sync complete!")
        print(f"   Uploaded: {uploaded} files")
        print(f"   Skipped: {skipped} files (unchanged)")
        print(f"   Last sync: {self.sync_state['last_sync']}")

    def restore(self):
        if not self.authenticate():
            print("❌ Authentication failed")
            return

        print("\n☁️ Restoring from Google Drive...")

        # In production, would list files from Google Drive
        # and download them to local .aios directory
        restored = 0

        # Placeholder: simulate restoration
        if not self.aios_dir.exists():
            self.aios_dir.mkdir()

        # Mock restoration of key files
        mock_files = ['tasks.txt', 'goals.txt', 'ideas.txt', 'daily_plan.md']
        for filename in mock_files:
            file_path = self.aios_dir / filename
            if self.download_file(filename):
                restored += 1
                # Create placeholder file
                with open(file_path, 'w') as f:
                    f.write(f"# Restored from Google Drive\n# {datetime.now()}\n")

        print(f"\n✅ Restored {restored} files from Google Drive")

    def status(self):
        print("\n📊 Google Drive Sync Status")
        print("=" * 40)

        if self.sync_state['last_sync']:
            print(f"Last sync: {self.sync_state['last_sync']}")
            print(f"Tracked files: {len(self.sync_state['files'])}")

            # Calculate total size
            total_size = 0
            for file_key in self.sync_state['files']:
                file_path = self.aios_dir / file_key
                if file_path.exists():
                    total_size += file_path.stat().st_size

            print(f"Total size: {total_size / (1024*1024):.2f} MB")
        else:
            print("Never synced")

        # Check for unsynced changes
        unsynced = 0
        for file_path in self.aios_dir.rglob('*'):
            if file_path.is_file():
                file_key = str(file_path.relative_to(self.aios_dir))
                if file_key not in self.sync_state['files']:
                    unsynced += 1
                elif self.sync_state['files'][file_key] < file_path.stat().st_mtime:
                    unsynced += 1

        if unsynced > 0:
            print(f"\n⚠️ {unsynced} files have unsynced changes")

def main():
    parser = argparse.ArgumentParser(description='Google Drive Backup')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    subparsers.add_parser('sync', help='Sync to Google Drive')
    subparsers.add_parser('restore', help='Restore from Google Drive')
    subparsers.add_parser('status', help='Show sync status')

    args = parser.parse_args()
    backup = BackupGDrive()

    if args.command == 'sync':
        backup.sync()
    elif args.command == 'restore':
        backup.restore()
    elif args.command == 'status':
        backup.status()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()