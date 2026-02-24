#!/usr/bin/env python3
"""
RClone Google Drive Manager - Local sync for instant file manager access.
Uses rclone bisync for bidirectional sync to ~/gdrive_{account}/ local folder.
Syncs every 5 minutes via systemd timer. Requires disk space but gives native speed.
"""

import subprocess
import os
import sys
import json
import time
import shutil
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import argparse
from datetime import datetime
import textwrap


class RCloneGDriveManager:
    """Manages rclone Google Drive setup with local bidirectional sync."""

    def __init__(self):
        self.home_dir = Path.home()
        self._sync_folder = None
        self.config_dir = self.home_dir / ".config" / "rclone"
        self.config_file = self.config_dir / "rclone.conf"
        self.systemd_dir = self.home_dir / ".config" / "systemd" / "user"
        self.service_name = "rclone-gdrive-sync.service"
        self.timer_name = "rclone-gdrive-sync.timer"
        self.service_file = self.systemd_dir / self.service_name
        self.timer_file = self.systemd_dir / self.timer_name
        self.remote_name = "backup-os"
        self.bin_dir = self.home_dir / "bin"
        self.sync_state_file = self.config_dir / "bisync_state"
        self.sync_interval = "5min"  # How often to sync

        # ANSI color codes for better terminal output
        self.GREEN = '\033[92m'
        self.YELLOW = '\033[93m'
        self.RED = '\033[91m'
        self.BLUE = '\033[94m'
        self.BOLD = '\033[1m'
        self.END = '\033[0m'

    @property
    def sync_folder(self):
        if not self._sync_folder:
            self._sync_folder = self.home_dir / f"gdrive_{self.get_account_name() or self.home_dir.name}"
        return self._sync_folder

    def get_account_name(self) -> Optional[str]:
        """Get Google account name (email prefix) from Drive API."""
        try:
            import re, urllib.request
            token = re.search(r'"access_token":"([^"]+)"', subprocess.run(
                [self.get_rclone_path(), "config", "show", self.remote_name], capture_output=True, text=True).stdout)
            if not token: return None
            req = urllib.request.Request("https://www.googleapis.com/drive/v3/about?fields=user",
                headers={"Authorization": f"Bearer {token.group(1)}"})
            return json.loads(urllib.request.urlopen(req, timeout=5).read()).get("user", {}).get("emailAddress", "").split("@")[0] or None
        except: return None

    def print_status(self, message: str, status: str = "info"):
        """Print formatted status messages with colors."""
        icons = {
            "success": f"{self.GREEN}✓{self.END}",
            "error": f"{self.RED}✗{self.END}",
            "warning": f"{self.YELLOW}⚠{self.END}",
            "info": f"{self.BLUE}ℹ{self.END}",
            "working": f"{self.YELLOW}⚙{self.END}"
        }
        icon = icons.get(status, icons["info"])
        print(f"{icon} {message}")

    def run_command(self, cmd: List[str], check: bool = True, capture_output: bool = True,
                   timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a command with error handling."""
        try:
            result = subprocess.run(
                cmd,
                check=check,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.CalledProcessError as e:
            if capture_output:
                self.print_status(f"Command failed: {' '.join(cmd)}", "error")
                if e.stderr:
                    print(f"  Error: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            self.print_status(f"Command timed out: {' '.join(cmd)}", "error")
            raise

    def get_rclone_path(self) -> str:
        """Get rclone binary path (system or ~/bin)."""
        if (self.bin_dir / "rclone").exists(): return str(self.bin_dir / "rclone")
        return "rclone"

    def check_rclone_installed(self) -> bool:
        """Check if rclone is installed (system or ~/bin)."""
        try:
            return subprocess.run([self.get_rclone_path(), "version"], capture_output=True).returncode == 0
        except: return False

    def check_rclone_update(self) -> bool:
        """Check if rclone outdated, offer to update. Returns True if ok to proceed."""
        import urllib.request, re
        cur = self.get_rclone_version() or ""
        try:
            with urllib.request.urlopen("https://downloads.rclone.org/version.txt", timeout=5) as r:
                lat = r.read().decode().strip()
            cv, lv = re.search(r'(\d+)\.(\d+)', cur), re.search(r'(\d+)\.(\d+)', lat)
            if cv and lv and (int(cv[1]), int(cv[2])) < (int(lv[1]), int(lv[2])):
                self.print_status(f"Outdated: {cur} → {lat} available", "warning")
                print(f"  Your distro package is behind. Latest has better bisync + bugfixes.")
                if input("Update to latest? [Y/n]: ").strip().lower() == 'n': return True
                if subprocess.run(["dpkg", "-s", "rclone"], capture_output=True).returncode == 0:
                    print("Removing apt version (enter password):")
                    subprocess.run(["sudo", "apt", "remove", "-y", "rclone"])
                return self.install_rclone()
        except: pass
        return True

    def install_rclone(self) -> bool:
        """Install latest rclone to ~/bin."""
        self.print_status("Installing latest rclone to ~/bin...", "working")
        try:
            self.bin_dir.mkdir(exist_ok=True)
            import urllib.request, zipfile, io
            with urllib.request.urlopen("https://downloads.rclone.org/rclone-current-linux-amd64.zip", timeout=60) as resp:
                with zipfile.ZipFile(io.BytesIO(resp.read())) as z:
                    for f in z.namelist():
                        if f.endswith("/rclone"):
                            (self.bin_dir / "rclone").write_bytes(z.read(f))
                            (self.bin_dir / "rclone").chmod(0o755)
                            self.print_status(f"Installed {self.get_rclone_version()} to ~/bin/rclone", "success")
                            return True
        except Exception as e: self.print_status(f"Installation error: {e}", "error")
        return False

    def get_rclone_version(self) -> Optional[str]:
        """Get the installed rclone version."""
        try:
            result = subprocess.run([self.get_rclone_path(), "version"], capture_output=True, text=True)
            return next((l.strip() for l in result.stdout.split('\n') if l.startswith('rclone')), None) if result.returncode == 0 else None
        except: return None

    def check_remote_configured(self) -> bool:
        """Check if Google Drive remote is already configured."""
        try:
            result = subprocess.run([self.get_rclone_path(), "listremotes"], capture_output=True, text=True)
            return f"{self.remote_name}:" in result.stdout.strip().split('\n') if result.returncode == 0 else False
        except: return False

    def configure_gdrive_interactive(self):
        """Launch interactive rclone configuration for Google Drive."""
        self.print_status("Launching interactive Google Drive configuration...", "info")
        print(f"\n{self.BOLD}Follow these steps:{self.END}")
        print("1. Type 'n' for new remote")
        print(f"2. Name it '{self.remote_name}'")
        print("3. Choose 'Google Drive' from the list")
        print("4. Follow the authentication steps\n")
        try:
            subprocess.run([self.get_rclone_path(), "config"])
            self.print_status("Configuration completed", "success")
        except Exception as e:
            self.print_status(f"Configuration failed: {e}", "error")

    def test_gdrive_connection(self) -> bool:
        """Test if Google Drive connection is working."""
        try:
            self.print_status("Testing Google Drive connection...", "working")
            result = subprocess.run([self.get_rclone_path(), "lsd", f"{self.remote_name}:", "--max-depth", "1"],
                capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                self.print_status("Google Drive connection successful", "success")
                return True
            self.print_status("Google Drive connection failed", "error")
        except: self.print_status("Connection test failed", "error")
        return False

    def get_gdrive_info(self) -> Optional[Dict]:
        """Get Google Drive storage information."""
        try:
            result = subprocess.run([self.get_rclone_path(), "about", f"{self.remote_name}:"], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return {k.strip(): v.strip() for line in result.stdout.split('\n') if ':' in line for k, v in [line.split(':', 1)]}
        except: pass
        return None

    def create_sync_folder(self) -> bool:
        """Create the sync folder directory."""
        try:
            self.sync_folder.mkdir(exist_ok=True)
            self.print_status(f"Sync folder created at {self.sync_folder}", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to create sync folder: {e}", "error")
            return False

    def is_synced(self) -> bool:
        """Check if sync folder exists and has been initialized."""
        return self.sync_folder.exists() and self.sync_state_file.exists()

    def is_timer_active(self) -> bool:
        """Check if sync timer is active."""
        try:
            result = self.run_command(["systemctl", "--user", "is-active", self.timer_name], check=False)
            return result.returncode == 0
        except:
            return False

    def get_last_sync_time(self) -> Optional[str]:
        """Get timestamp of last successful sync."""
        if self.sync_state_file.exists():
            try:
                mtime = self.sync_state_file.stat().st_mtime
                return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            except: pass
        return None

    def run_bisync(self, resync: bool = False, dry_run: bool = False) -> bool:
        """Run rclone bisync between remote and local folder."""
        self.sync_folder.mkdir(exist_ok=True)
        for lck in (self.home_dir / ".cache" / "rclone" / "bisync").glob("*.lck"): lck.unlink(missing_ok=True)
        cmd = [self.get_rclone_path(), "bisync", f"{self.remote_name}:", str(self.sync_folder),
               "--transfers", "20", "--checkers", "20", "--fast-list", "--progress",
               "--log-file", str(self.config_dir / "rclone-sync.log"), "--log-level", "INFO"]
        if resync: cmd.append("--resync")
        if dry_run: cmd.append("--dry-run")
        try:
            self.print_status(f"{'Resyncing' if resync else 'Syncing'} Google Drive... (Ctrl+C to cancel)", "working")
            result = subprocess.run(cmd, timeout=3600)
            if result.returncode == 0:
                self.sync_state_file.parent.mkdir(parents=True, exist_ok=True)
                self.sync_state_file.write_text(datetime.now().isoformat())
                self.print_status("Sync completed successfully", "success")
                return True
            else:
                self.print_status(f"Sync failed (exit code {result.returncode}) - check logs: {self.config_dir}/rclone-sync.log", "error")
                return False
        except subprocess.TimeoutExpired:
            self.print_status("Sync timed out after 1 hour", "error")
            return False
        except Exception as e:
            self.print_status(f"Sync error: {e}", "error")
            return False

    def sync_drive(self, initial: bool = False) -> bool:
        """Sync Google Drive to local folder. Use initial=True for first sync."""
        if not self.check_remote_configured():
            self.print_status("Google Drive remote not configured", "error")
            return False
        # First sync requires --resync flag
        needs_resync = initial or not self.sync_state_file.exists()
        if needs_resync:
            self.print_status("Performing initial sync (this may take a while)...", "info")
        return self.run_bisync(resync=needs_resync)

    def stop_sync(self, remove_local: bool = False) -> bool:
        """Stop sync timer and optionally remove local folder."""
        if self.timer_file.exists():
            self.run_command(["systemctl", "--user", "stop", self.timer_name], check=False)
            self.run_command(["systemctl", "--user", "disable", self.timer_name], check=False)
            self.print_status("Sync timer stopped", "success")
        if remove_local and self.sync_folder.exists():
            response = input(f"Remove local folder {self.sync_folder}? (y/N): ")
            if response.lower() == 'y':
                shutil.rmtree(self.sync_folder)
                self.print_status("Local folder removed", "success")
        return True

    def create_systemd_service(self) -> bool:
        """Create systemd service and timer for periodic sync."""
        self.print_status("Creating systemd sync service and timer...", "working")
        service_content = f"""[Unit]
Description=RClone Google Drive Bisync
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={self.get_rclone_path()} bisync {self.remote_name}: {self.sync_folder} --transfers 20 --checkers 20 --fast-list --log-file {self.config_dir}/rclone-sync.log --log-level INFO
TimeoutSec=3600"""

        timer_content = f"""[Unit]
Description=RClone Google Drive Sync Timer

[Timer]
OnBootSec=1min
OnUnitActiveSec={self.sync_interval}
Persistent=true

[Install]
WantedBy=timers.target"""
        try:
            self.systemd_dir.mkdir(parents=True, exist_ok=True)
            self.service_file.write_text(service_content)
            self.timer_file.write_text(timer_content)
            self.run_command(["systemctl", "--user", "daemon-reload"])
            self.print_status("Systemd service and timer created", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to create service: {e}", "error")
            return False

    def enable_service(self) -> bool:
        """Enable the sync timer for auto-start."""
        try:
            self.run_command(["systemctl", "--user", "enable", self.timer_name])
            self.run_command(["systemctl", "--user", "start", self.timer_name])
            self.print_status("Sync timer enabled and started", "success")
            return True
        except:
            self.print_status("Failed to enable timer", "error")
            return False

    def disable_service(self) -> bool:
        """Disable the sync timer."""
        try:
            self.run_command(["systemctl", "--user", "stop", self.timer_name], check=False)
            self.run_command(["systemctl", "--user", "disable", self.timer_name], check=False)
            self.print_status("Sync timer disabled", "success")
            return True
        except:
            self.print_status("Failed to disable timer", "error")
            return False

    def start_service(self) -> bool:
        """Start a sync now (runs the service once)."""
        try:
            self.run_command(["systemctl", "--user", "start", self.service_name])
            self.print_status("Sync started", "success")
            return True
        except:
            self.print_status("Failed to start sync", "error")
            return False

    def stop_service(self) -> bool:
        """Stop the sync timer."""
        try:
            self.run_command(["systemctl", "--user", "stop", self.timer_name], check=False)
            self.print_status("Sync timer stopped", "success")
            return True
        except:
            self.print_status("Failed to stop service", "error")
            return False

    def get_service_status(self) -> str:
        """Get the status of the sync timer."""
        try:
            result = self.run_command(["systemctl", "--user", "is-active", self.timer_name], check=False)
            return result.stdout.strip()
        except:
            return "unknown"

    def add_file_manager_bookmark(self) -> bool:
        """Add Google Drive to file manager bookmarks."""
        self.print_status("Adding file manager bookmark...", "working")
        bookmark_file = self.home_dir / ".config" / "gtk-3.0" / "bookmarks"
        bookmark_entry = f"file://{self.sync_folder} GoogleDrive\n"
        try:
            bookmark_file.parent.mkdir(parents=True, exist_ok=True)
            if bookmark_file.exists() and str(self.sync_folder) in bookmark_file.read_text():
                self.print_status("Bookmark already exists", "info")
                return True
            with open(bookmark_file, 'a') as f:
                f.write(bookmark_entry)
            self.print_status("File manager bookmark added", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to add bookmark: {e}", "error")
            return False

    def create_desktop_entry(self) -> bool:
        """Create desktop application entry."""
        self.print_status("Creating desktop entry...", "working")
        desktop_dir = self.home_dir / ".local" / "share" / "applications"
        desktop_file = desktop_dir / "google-drive.desktop"
        desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Google Drive
Comment=Open Google Drive folder
Icon=folder-google-drive
Exec=xdg-open {self.sync_folder}
Categories=Network;FileTransfer;
Terminal=false
StartupNotify=true"""
        try:
            desktop_dir.mkdir(parents=True, exist_ok=True)
            desktop_file.write_text(desktop_content)
            self.run_command(["update-desktop-database", str(desktop_dir)], check=False)
            self.print_status("Desktop entry created", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to create desktop entry: {e}", "error")
            return False

    def create_helper_scripts(self) -> bool:
        """Create helper scripts for syncing."""
        self.print_status("Creating helper scripts...", "working")
        self.bin_dir.mkdir(exist_ok=True)
        sync_script = self.bin_dir / "sync-gdrive"
        sync_content = f"""#!/bin/bash
# Sync Google Drive
echo "Syncing Google Drive to {self.sync_folder}..."
rclone bisync {self.remote_name}: {self.sync_folder} --transfers 20 --checkers 20 --fast-list
echo "Sync complete!"
xdg-open {self.sync_folder}"""
        try:
            sync_script.write_text(sync_content)
            sync_script.chmod(0o755)
            self.print_status("Helper script created: ~/bin/sync-gdrive", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to create scripts: {e}", "error")
            return False

    def show_status(self):
        """Display comprehensive status information."""
        print(f"\n{self.BOLD}=== RClone Google Drive Status ==={self.END}\n")
        if self.check_rclone_installed():
            self.print_status(f"RClone: {self.get_rclone_version() or 'Installed'}", "success")
        else:
            self.print_status("RClone: Not installed", "error"); return
        if self.check_remote_configured():
            self.print_status(f"Remote '{self.remote_name}': Configured", "success")
            if info := self.get_gdrive_info():
                print(f"  Storage: {info.get('Total', 'N/A')} | Used: {info.get('Used', 'N/A')} | Free: {info.get('Free', 'N/A')}")
        else:
            self.print_status(f"Remote '{self.remote_name}': Not configured - run 'setup'", "error"); return
        if self.is_synced():
            self.print_status(f"Sync: Active at {self.sync_folder}", "success")
            if last := self.get_last_sync_time(): print(f"  Last sync: {last}")
        else:
            self.print_status(f"Sync: Not initialized - run 'sync' or 'setup'", "warning")
        if self.timer_file.exists():
            status = self.get_service_status()
            self.print_status(f"Timer: {status}", "success" if status == "active" else "warning")
        else:
            self.print_status("Timer: Not installed", "warning")
        bookmark_file = self.home_dir / ".config" / "gtk-3.0" / "bookmarks"
        if bookmark_file.exists() and str(self.sync_folder) in bookmark_file.read_text():
            self.print_status("File Manager: Bookmark added", "success")
        print()

    def full_setup(self):
        """Perform complete setup of rclone with Google Drive."""
        print(f"\n{self.BOLD}=== RClone Google Drive Setup ==={self.END}\n")
        if not self.check_rclone_installed() and not self.install_rclone():
            self.print_status("Please install rclone manually", "error"); return False
        if not self.check_rclone_update(): return False
        if not self.check_remote_configured() or not self.test_gdrive_connection():
            self.print_status("Not signed in - please sign in to Google Drive", "info")
            self.configure_gdrive_interactive()
            if not self.check_remote_configured() or not self.test_gdrive_connection():
                self.print_status("Google Drive sign-in required", "error"); return False
        info = self.get_gdrive_info()
        used = info.get('Used', 'unknown') if info else 'unknown'
        print(f"\n{self.YELLOW}{self.BOLD}WARNING:{self.END} This will copy ALL Google Drive files locally ({used} used).")
        print(f"This requires equivalent local disk space and may take a long time.")
        if input("Continue with full sync? (y/N): ").lower() != 'y': return False
        self.create_sync_folder()
        if not self.sync_drive(initial=True):
            self.print_status("Initial sync failed - check connection and try 'sync' again", "error"); return False
        if self.create_systemd_service(): self.enable_service()
        self.add_file_manager_bookmark()
        self.create_desktop_entry()
        self.create_helper_scripts()
        print(f"\n{self.GREEN}{self.BOLD}Setup completed successfully!{self.END}")
        print(f"Your Google Drive is synced to: {self.sync_folder}")
        print(f"Auto-sync every {self.sync_interval} via systemd timer.")
        return True

    def watch_logs(self):
        """Watch rclone sync logs in real-time."""
        log_file = self.config_dir / "rclone-sync.log"
        if not log_file.exists():
            self.print_status(f"No log file found at {log_file}", "error"); return
        print(f"{self.BOLD}Watching rclone logs (Ctrl+C to stop){self.END}\n")
        subprocess.run(["tail", "-f", str(log_file)])

    def upload(self, source: str, dest: str, sync: bool = False) -> bool:
        """One-time upload of a folder to Google Drive.

        Args:
            source: Local folder path to upload
            dest: Destination path on Google Drive (e.g., "Backups/myproject")
            sync: If True, use sync (mirror source exactly). If False, use copy (additive).
        """
        source_path = Path(source).expanduser().resolve()
        if not source_path.exists():
            self.print_status(f"Source path does not exist: {source_path}", "error")
            return False

        if not self.check_remote_configured():
            self.print_status("Google Drive remote not configured. Run 'setup' first.", "error")
            return False

        # Build remote destination path
        remote_dest = f"{self.remote_name}:{dest.strip('/')}" if dest else f"{self.remote_name}:"

        # Use sync or copy based on flag
        operation = "sync" if sync else "copy"
        cmd = [
            self.get_rclone_path(), operation,
            str(source_path), remote_dest,
            "--transfers", "10",
            "--checkers", "10",
            "--progress",
            "-v"
        ]

        self.print_status(f"Uploading {source_path} -> {remote_dest}", "working")
        print(f"  Operation: {operation} ({'mirror' if sync else 'additive'})")

        try:
            result = subprocess.run(cmd)
            if result.returncode == 0:
                self.print_status(f"Upload complete: {remote_dest}", "success")
                return True
            else:
                self.print_status(f"Upload failed (exit code {result.returncode})", "error")
                return False
        except KeyboardInterrupt:
            self.print_status("Upload cancelled", "warning")
            return False
        except Exception as e:
            self.print_status(f"Upload error: {e}", "error")
            return False

    def backup(self, source: str, dest: str = "backups") -> bool:
        """Backup a drive/folder to Google Drive with optimized settings."""
        cmd = [self.get_rclone_path(), "copy", source, f"{self.remote_name}:{dest}",
               "--transfers", "16", "--checkers", "32", "--drive-chunk-size", "128M",
               "--progress", "-v"]
        self.print_status(f"Backing up {source} -> {self.remote_name}:{dest}", "working")
        return subprocess.run(cmd).returncode == 0

    def remove(self):
        """Remove everything: services, remote config, folder, scripts."""
        for cmd in [["systemctl", "--user", "stop", self.timer_name], ["systemctl", "--user", "disable", self.timer_name]]:
            subprocess.run(cmd, capture_output=True)
        for f in [self.timer_file, self.service_file]: f.unlink(missing_ok=True)
        subprocess.run([self.get_rclone_path(), "config", "delete", self.remote_name], capture_output=True)
        bm = self.home_dir / ".config" / "gtk-3.0" / "bookmarks"
        if bm.exists(): bm.write_text('\n'.join(l for l in bm.read_text().split('\n') if "gdrive" not in l.lower()))
        for f in [self.home_dir/".local"/"share"/"applications"/"google-drive.desktop", self.bin_dir/"sync-gdrive"]: f.unlink(missing_ok=True)
        for d in self.home_dir.glob("gdrive_*"): shutil.rmtree(d)
        if (self.bin_dir/"rclone").exists(): (self.bin_dir/"rclone").unlink()
        self.print_status("Removed", "success")


def main():
    """Main entry point with CLI argument parsing."""
    m = RCloneGDriveManager()
    if len(sys.argv) == 1:
        print(f"\n{m.BOLD}rclone.py - Google Drive Manager{m.END}\n")
        print(f"  1) status   2) setup   3) sync    4) upload")
        print(f"  5) backup   6) service 7) logs    8) remove  0) exit\n")
        try:
            c = input("Select: ").strip()
            if c and c != '0':
                cmd = ['', 'status', 'setup', 'sync', 'upload', 'backup', 'service', 'logs', 'remove'][int(c)]
                import os; os.execvp(sys.executable, [sys.executable, sys.argv[0], cmd])
        except: pass
        return
    parser = argparse.ArgumentParser(prog="rclone.py", description="RClone Google Drive Bisync Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=textwrap.dedent("""
        Examples:
          %(prog)s setup              # Install rclone + configure + initial sync
          %(prog)s sync [--resync]    # Run bidirectional sync (--resync for full resync)
          %(prog)s status             # Show current status
          %(prog)s service start|stop|enable|disable
          %(prog)s upload <source> <dest> [--sync]  # One-time upload to Drive
          %(prog)s logs | remove
        """))
    parser.add_argument('action', choices=['setup', 'sync', 'status', 'service', 'logs', 'remove', 'upload', 'backup'])
    parser.add_argument('subaction', nargs='?')
    parser.add_argument('dest', nargs='?', help='Destination path for upload (e.g., "Backups/project")')
    parser.add_argument('--resync', action='store_true', help='Force full resync')
    parser.add_argument('--sync', action='store_true', help='For upload: mirror source exactly (delete extra files at dest)')
    args = parser.parse_args()
    if args.action == 'setup': m.full_setup()
    elif args.action == 'sync': m.sync_drive(initial=args.resync) and print(f"Files at: {m.sync_folder}")
    elif args.action == 'status': m.show_status()
    elif args.action == 'service':
        if args.subaction not in ['start', 'stop', 'enable', 'disable']:
            print("Usage: service start|stop|enable|disable"); sys.exit(1)
        {'start': m.start_service, 'stop': m.stop_service, 'enable': m.enable_service, 'disable': m.disable_service}[args.subaction]()
    elif args.action == 'upload':
        if not args.subaction:
            print("Usage: upload <source_folder> <dest_path> [--sync]")
            print("  source_folder: Local folder to upload")
            print("  dest_path: Destination on Google Drive (e.g., 'Backups/myproject')")
            print("  --sync: Mirror source exactly (deletes extra files at dest)")
            sys.exit(1)
        dest = args.dest or ""
        m.upload(args.subaction, dest, sync=args.sync)
    elif args.action == 'backup':
        if not args.subaction:
            print("Usage: backup <source> [dest] [--max-size 10M]")
            sys.exit(1)
        m.backup(args.subaction, args.dest or "backups")
    elif args.action == 'logs': m.watch_logs()
    elif args.action == 'remove' and input("Remove all? (y/N): ").lower() == 'y': m.remove()

if __name__ == "__main__":
    main()