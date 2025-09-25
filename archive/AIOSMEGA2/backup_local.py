#!/usr/bin/env python3
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime, timedelta

class BackupLocal:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.backup_base = Path.home() / ".aios_backup"
        self.backup_base.mkdir(exist_ok=True)
        self.backup_log = self.backup_base / "backup.log"

    def get_backup_dir(self, date=None):
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        return self.backup_base / date

    def backup_now(self):
        backup_dir = self.get_backup_dir()
        backup_dir.mkdir(exist_ok=True)

        if not self.aios_dir.exists():
            print("❌ No .aios directory found")
            return

        copied_files = 0
        skipped_files = 0

        for file_path in self.aios_dir.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(self.aios_dir)
                target_path = backup_dir / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Check if file has changed
                if target_path.exists():
                    if file_path.stat().st_mtime <= target_path.stat().st_mtime:
                        skipped_files += 1
                        continue

                shutil.copy2(file_path, target_path)
                copied_files += 1

        # Log the backup
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'copied': copied_files,
            'skipped': skipped_files,
            'backup_dir': str(backup_dir)
        }

        with open(self.backup_log, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

        print(f"✅ Backup complete: {copied_files} files copied, {skipped_files} unchanged")
        print(f"📁 Backup location: {backup_dir}")

        # Clean old backups
        self.clean_old_backups()

    def clean_old_backups(self, keep_days=7):
        cutoff = datetime.now() - timedelta(days=keep_days)

        for backup_dir in self.backup_base.iterdir():
            if backup_dir.is_dir() and backup_dir.name != 'backup.log':
                try:
                    dir_date = datetime.strptime(backup_dir.name, '%Y-%m-%d')
                    if dir_date < cutoff:
                        shutil.rmtree(backup_dir)
                        print(f"🗑 Removed old backup: {backup_dir.name}")
                except ValueError:
                    pass  # Skip non-date directories

    def restore_backup(self, date):
        backup_dir = self.get_backup_dir(date)

        if not backup_dir.exists():
            print(f"❌ No backup found for {date}")
            self.list_backups()
            return

        if not self.aios_dir.exists():
            self.aios_dir.mkdir()

        restored = 0
        for file_path in backup_dir.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(backup_dir)
                target_path = self.aios_dir / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_path)
                restored += 1

        print(f"✅ Restored {restored} files from {date}")

    def list_backups(self):
        print("\n=== Available Backups ===")
        backups = []

        for backup_dir in sorted(self.backup_base.iterdir()):
            if backup_dir.is_dir() and backup_dir.name != 'backup.log':
                file_count = len(list(backup_dir.rglob('*')))
                size = sum(f.stat().st_size for f in backup_dir.rglob('*') if f.is_file())
                size_mb = size / (1024 * 1024)
                backups.append((backup_dir.name, file_count, size_mb))

        if backups:
            for date, files, size in backups:
                print(f"📅 {date}: {files} files ({size:.2f} MB)")
        else:
            print("No backups found")

def main():
    parser = argparse.ArgumentParser(description='Local Backup Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    subparsers.add_parser('now', help='Create backup now')
    subparsers.add_parser('list', help='List available backups')

    restore_parser = subparsers.add_parser('restore', help='Restore from backup')
    restore_parser.add_argument('date', help='Backup date (YYYY-MM-DD)')

    args = parser.parse_args()
    backup = BackupLocal()

    if args.command == 'now':
        backup.backup_now()
    elif args.command == 'list':
        backup.list_backups()
    elif args.command == 'restore':
        backup.restore_backup(args.date)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()