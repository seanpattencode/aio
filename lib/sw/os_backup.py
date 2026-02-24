#!/usr/bin/env python3
"""
OS Backup - Resumable backup tool for Android and Windows to Google Drive.
"""
import subprocess, os, json, hashlib, sys, time, argparse
from pathlib import Path

TMP = Path("/tmp/os_backup")
REMOTE = "backup-os"
CHUNK_MB = 100

def fmt_size(b):
    if b >= 1024**3: return f"{b/1024**3:.1f}GB"
    if b >= 1024**2: return f"{b/1024**2:.0f}MB"
    if b >= 1024: return f"{b/1024:.0f}KB"
    return f"{b}B"

def load_manifest(path):
    if path.exists():
        return json.loads(path.read_text())
    return {"copied": {}, "total_bytes": 0}

def save_manifest(path, m):
    path.write_text(json.dumps(m, indent=2))

def prompt(msg):
    try:
        return input(msg).strip().lower()
    except EOFError:
        return 'n'

# ============================================================
# ANDROID BACKUP
# ============================================================
def find_adb():
    """Find adb binary, checking common SDK locations."""
    if subprocess.run(["which", "adb"], capture_output=True).returncode == 0:
        return "adb"
    for p in [Path.home() / "Android/Sdk/platform-tools/adb", Path("/opt/android-sdk/platform-tools/adb")]:
        if p.exists(): return str(p)
    return "adb"  # fallback

ADB = find_adb()

def adb_shell(cmd):
    return subprocess.run([ADB, "shell", cmd], capture_output=True, text=True).stdout

def get_adb_files(remote):
    out = adb_shell(f"find {remote} -type f -exec stat -c '%s %n' {{}} \\; 2>/dev/null")
    files = []
    for line in out.strip().split('\n'):
        if ' ' in line:
            parts = line.split(' ', 1)
            if len(parts) == 2 and parts[0].isdigit():
                files.append((int(parts[0]), parts[1]))
    return sorted(files)

def get_adb_folder_size(remote):
    out = adb_shell(f"du -sb {remote} 2>/dev/null").strip().split()
    return int(out[0]) if out and out[0].isdigit() else 0

def backup_android(mode="smart"):
    SMART_FOLDERS = ["/sdcard/DCIM", "/sdcard/Download", "/sdcard/Pictures",
                     "/sdcard/Documents", "/sdcard/Music", "/sdcard/Movies"]
    SKIP_FOLDERS = {"Android", ".thumbnails", ".cache", "lost+found"}  # caches, not user data

    if mode == "full":
        # Discover ALL folders in /sdcard dynamically
        out = adb_shell("ls -1 /sdcard/").strip().split('\n')
        FOLDERS = [f"/sdcard/{f.strip()}" for f in out if f.strip() and f.strip() not in SKIP_FOLDERS]
        FOLDERS.append("/sdcard/Android/media")  # App media (WhatsApp images) but not Android/data (caches)
    else:
        FOLDERS = SMART_FOLDERS
    FOLDERS = [f for f in FOLDERS if adb_shell(f"[ -d {f} ] && echo yes").strip() == "yes"]

    backup_dir = TMP / "android" / mode
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = backup_dir / "manifest.json"
    m = load_manifest(manifest_path)

    print("=" * 50)
    print("        ANDROID BACKUP")
    print("=" * 50)
    print(f"Mode: {mode.upper()}\n")

    print("┌─ LIMITATIONS (No Root) ─────────────────────────┐")
    print("│ ✗ App data (/data/data/) - settings, databases  │")
    print("│ ✗ SMS/Call logs - need app export               │")
    print("│ ✗ Contacts - need Google/app sync               │")
    print("│ ✗ WhatsApp chats - encrypted, need app export   │")
    print("│ ✗ App login tokens/sessions                     │")
    print("│ ✗ System settings                               │")
    print("├─ WHAT WE CAN BACKUP ────────────────────────────┤")
    print("│ ✓ Photos & Videos (DCIM)                        │")
    print("│ ✓ Downloads, Documents, Music, Movies           │")
    print("│ ✓ WhatsApp media (images/videos, not chats)     │")
    print("│ ✓ APKs (app installers, not data)               │")
    print("│ ✓ ADB backup (apps that allow it, ~20%)         │")
    print("└─────────────────────────────────────────────────┘\n")

    # Check ADB connection
    result = subprocess.run([ADB, "devices"], capture_output=True, text=True)
    if "device" not in result.stdout.split('\n')[1]:
        print("✗ No Android device connected via ADB")
        return

    device_name = adb_shell("getprop ro.product.model").strip().replace(" ", "_") or "unknown"
    print(f"Device: {device_name}\n")

    print("Scanning phone...")
    total_on_phone = sum(get_adb_folder_size(f) for f in FOLDERS)
    already_copied = m["total_bytes"]

    print(f"\n{'OVERALL STATUS':=^50}")
    print(f"  Phone total:    {fmt_size(total_on_phone)}")
    print(f"  Already copied: {fmt_size(already_copied)}")
    print(f"  Remaining:      {fmt_size(max(0, total_on_phone - already_copied))}")
    if total_on_phone > 0:
        pct = min(100, (already_copied / total_on_phone) * 100)
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        print(f"  Progress:       [{bar}] {pct:.0f}%")
    print("=" * 50 + "\n")

    # Backup folders
    chunk_remaining = CHUNK_MB * 1024 * 1024
    copied_this_run = 0

    for i, folder in enumerate(FOLDERS, 1):
        name = folder.split('/')[-1]
        local = backup_dir / name
        local.mkdir(parents=True, exist_ok=True)

        folder_size = get_adb_folder_size(folder)
        folder_copied = sum(v["size"] for k, v in m["copied"].items() if k.startswith(folder))
        status = "✓" if folder_copied >= folder_size else "◐" if folder_copied > 0 else "○"
        print(f"[{i}/{len(FOLDERS)}] {status} {name}: {fmt_size(folder_copied)}/{fmt_size(folder_size)}")

        if chunk_remaining > 0 and folder_copied < folder_size:
            files = get_adb_files(folder)
            for size, remote_path in files:
                if chunk_remaining <= 0:
                    break
                if remote_path in m["copied"]:
                    continue
                fname = os.path.basename(remote_path)
                subprocess.run([ADB, "pull", remote_path, str(local) + "/"], capture_output=True)
                dst = local / fname
                if dst.exists():
                    m["copied"][remote_path] = {"size": size}
                    m["total_bytes"] += size
                    copied_this_run += size
                    chunk_remaining -= size
                    save_manifest(manifest_path, m)
            if copied_this_run > 0:
                print(f"      +{fmt_size(copied_this_run)} this run")

    # Full ADB backup
    print(f"\n[{len(FOLDERS)+1}] Full ADB backup")
    backup_file = backup_dir / "backup.ab"
    if backup_file.exists():
        print(f"      ✓ Exists: {fmt_size(backup_file.stat().st_size)}")
    elif prompt("      Run full backup? (y/n): ") == 'y':
        print("      Confirm on phone...")
        proc = subprocess.Popen([ADB, "backup", "-apk", "-shared", "-nosystem", "-f", str(backup_file)])
        while proc.poll() is None:
            if backup_file.exists():
                print(f"\r      Backing up... {fmt_size(backup_file.stat().st_size)}", end="", flush=True)
            time.sleep(1)
        print()

    # Summary & Upload
    print(f"\n{'SUMMARY':=^50}")
    print(f"  Copied: {fmt_size(m['total_bytes'])}")
    print(f"  Folder: {backup_dir}")
    print("=" * 50)

    date = time.strftime("%Y-%m-%d")
    upload_to_drive(backup_dir, f"{REMOTE}:os-backup/android/{device_name}/{date}_{mode}")

# ============================================================
# WINDOWS BACKUP
# ============================================================
def get_local_files(path):
    """Get all files with sizes from local path."""
    files = []
    try:
        for f in Path(path).rglob("*"):
            if f.is_file():
                try:
                    files.append((f.stat().st_size, str(f)))
                except:
                    pass
    except:
        pass
    return sorted(files)

def get_local_size(path):
    """Get total size of local folder."""
    total = 0
    try:
        for f in Path(path).rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except:
                    pass
    except:
        pass
    return total

def backup_windows(mode="smart", device_name=None):
    # Find Windows mount - check common locations directly
    print("=" * 50)
    print("        WINDOWS BACKUP")
    print("=" * 50)
    print("\nSearching for Windows partition...")

    win_path = None
    candidates = [
        Path("/media") / os.environ.get("USER", "") / "Windows",
        Path("/mnt/windows"),
        Path("/mnt/Windows"),
    ]

    for p in candidates:
        # Check both /mount/Windows/System32 and /mount/System32
        if (p / "Windows" / "System32").exists():
            win_path = p
            break
        elif (p / "System32").exists():
            win_path = p.parent  # Go up one level
            break

    if not win_path or not win_path.exists():
        print("\n✗ Windows partition not mounted")
        print("\nMount it with:")
        print("  udisksctl mount -b /dev/<partition>")
        print("  # or")
        print("  sudo mount -t ntfs3 /dev/<partition> /mnt/windows -o ro")
        return

    print(f"\nFound: {win_path}")
    print(f"Mode: {mode.upper()}\n")

    if mode == "full":  # rclone directly (don't scan/copy 300GB to /tmp)
        hostname = device_name or subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
        date = time.strftime("%Y-%m-%d")

        # Check for existing backup to resume
        existing = subprocess.run(["rclone", "lsd", f"{REMOTE}:os-backup/windows/{hostname}/"],
                                  capture_output=True, text=True)
        today_full = [l for l in existing.stdout.split('\n') if f"{date}_full" in l]
        if today_full:
            remote = f"{REMOTE}:os-backup/windows/{hostname}/{date}_full"
            print(f"Resuming existing backup: {remote}")
        else:
            remote = f"{REMOTE}:os-backup/windows/{hostname}/{date}_full"

        # Exclusions for Windows system files
        excludes = ["--exclude", "pagefile.sys", "--exclude", "hiberfil.sys",
                    "--exclude", "swapfile.sys", "--exclude", "$Recycle.Bin/**",
                    "--exclude", "System Volume Information/**"]

        # Check if rclone already running
        ps = subprocess.run(["pgrep", "-f", f"^rclone sync.*{hostname}"], capture_output=True, text=True)
        if ps.returncode == 0:
            print("Backup already running. Use 'ps aux | grep rclone' to monitor.")
            return
        # Show progress
        print("Checking progress...")
        sz = subprocess.run(["rclone", "size", remote, "--json"], capture_output=True, text=True)
        remote_bytes = json.loads(sz.stdout).get("bytes", 0) if sz.stdout.strip() else 0
        remote_count = json.loads(sz.stdout).get("count", 0) if sz.stdout.strip() else 0
        local_bytes = int(subprocess.run(["du", "-sb", str(win_path)], capture_output=True, text=True).stdout.split()[0])
        pct = (remote_bytes / local_bytes * 100) if local_bytes else 0
        print(f"  Done: {fmt_size(remote_bytes)} / {fmt_size(local_bytes)} ({pct:.0f}%) - {remote_count} files")
        if pct >= 99:
            print("  ✓ Backup complete")
            return
        if prompt(f"Resume? (y/n): ") == 'y':
            subprocess.run(["rclone", "sync", str(win_path), remote, "--transfers", "16", "--progress"] + excludes)
        return

    # Smart mode - user data only, no caches
    system_users = {"All Users", "Default", "Default User", "Public", "defaultuser100000"}
    users_path = win_path / "Users"
    user_folders = []

    if users_path.exists():
        for u in users_path.iterdir():
            if u.is_dir() and u.name not in system_users and not u.name.startswith("."):
                if (u / "Desktop").exists() or (u / "Documents").exists():
                    user_folders.append(u.name)

    print(f"Found users: {', '.join(user_folders) or 'none'}\n")

    # Build folders to backup from each user
    FOLDERS = []
    standard = ["Documents", "Desktop", "Downloads", "Pictures", "Music", "Videos", "source"]
    for user in user_folders:
        user_path = users_path / user
        for sub in standard:
            p = user_path / sub
            if p.exists():
                FOLDERS.append((f"{user}/{sub}", p))
        for item in user_path.iterdir():
            if item.is_dir() and "OneDrive" in item.name:
                FOLDERS.append((f"{user}/{item.name}", item))

    if not FOLDERS:
        print("✗ No user folders found to backup")
        return

    backup_dir = TMP / "windows" / "smart"
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = backup_dir / "manifest.json"
    m = load_manifest(manifest_path)

    print("Scanning Windows drive...")
    total_on_disk = sum(get_local_size(p) for _, p in FOLDERS)
    already_copied = m["total_bytes"]

    print(f"\n{'OVERALL STATUS':=^50}")
    print(f"  Disk total:     {fmt_size(total_on_disk)}")
    print(f"  Already copied: {fmt_size(already_copied)}")
    print(f"  Remaining:      {fmt_size(max(0, total_on_disk - already_copied))}")
    if total_on_disk > 0:
        pct = min(100, (already_copied / total_on_disk) * 100)
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        print(f"  Progress:       [{bar}] {pct:.0f}%")
    print("=" * 50 + "\n")

    # Backup folders
    chunk_remaining = CHUNK_MB * 1024 * 1024
    copied_this_run = 0

    for i, (name, src_path) in enumerate(FOLDERS, 1):
        local = backup_dir / name
        local.mkdir(parents=True, exist_ok=True)

        folder_size = get_local_size(src_path)
        folder_copied = sum(v["size"] for k, v in m["copied"].items() if k.startswith(str(src_path)))
        status = "✓" if folder_copied >= folder_size else "◐" if folder_copied > 0 else "○"
        print(f"[{i}/{len(FOLDERS)}] {status} {name}: {fmt_size(folder_copied)}/{fmt_size(folder_size)}")

        if chunk_remaining > 0 and folder_copied < folder_size:
            files = get_local_files(src_path)
            for size, src_file in files:
                if chunk_remaining <= 0:
                    print(f"      Chunk limit reached")
                    break
                if src_file in m["copied"]:
                    continue
                if size > 100 * 1024 * 1024:  # Skip files > 100MB for now
                    continue

                # Preserve relative path
                rel = Path(src_file).relative_to(src_path)
                dst = local / rel
                dst.parent.mkdir(parents=True, exist_ok=True)

                try:
                    import shutil
                    shutil.copy2(src_file, dst)
                    m["copied"][src_file] = {"size": size}
                    m["total_bytes"] += size
                    copied_this_run += size
                    chunk_remaining -= size
                    save_manifest(manifest_path, m)
                except Exception as e:
                    pass  # Skip permission errors

            if copied_this_run > 0:
                print(f"      +{fmt_size(copied_this_run)} this run")

    # Summary & Upload
    print(f"\n{'SUMMARY':=^50}")
    print(f"  Copied: {fmt_size(m['total_bytes'])}")
    print(f"  Folder: {backup_dir}")
    print("=" * 50)

    hostname = device_name or subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
    date = time.strftime("%Y-%m-%d")
    upload_to_drive(backup_dir, f"{REMOTE}:os-backup/windows/{hostname}/{date}_{mode}")

# ============================================================
# UPLOAD TO DRIVE
# ============================================================
def upload_to_drive(local_path, remote):
    print(f"\nUpload to Google Drive")
    local_size = sum(f.stat().st_size for f in Path(local_path).rglob("*") if f.is_file())
    print(f"  Local:  {local_path}")
    print(f"  Remote: {remote}")
    print(f"  Size:   {fmt_size(local_size)}")

    if prompt("  Upload? (y/n): ") == 'y':
        print("  Uploading...")
        proc = subprocess.Popen(
            ["rclone", "copy", str(local_path), remote, "--transfers", "16", "--progress"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            if "Transferred:" in line:
                print(f"\r  {line.strip()[:55]}", end="", flush=True)
        proc.wait()
        print()
        if proc.returncode == 0:
            print(f"  ✓ Uploaded to {remote}")
        else:
            print("  ✗ Upload failed")

# ============================================================
# MAIN
# ============================================================
def show_status():
    """Show status of recent backups and any running."""
    print("OS BACKUP STATUS")
    print("=" * 50)

    # Check running
    ps = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    running = [l for l in ps.stdout.split('\n') if 'rclone' in l and 'os-backup' in l and ('copy' in l or 'sync' in l)]
    if running:
        print("⟳ RUNNING:")
        for line in running:
            if 'android' in line: print("  • Android backup in progress")
            elif 'windows' in line: print("  • Windows backup in progress")

    # Check GDrive for all backups
    result = subprocess.run(["rclone", "lsd", f"{REMOTE}:os-backup/", "--max-depth", "3"],
                          capture_output=True, text=True)
    if result.returncode == 0:
        print("\n✓ COMPLETED (in Google Drive):")
        for platform in ["android", "windows"]:
            # Match folders with date pattern like 2026-01-25_full or _smart
            folders = sorted([l.split()[-1] for l in result.stdout.split('\n')
                      if f"{platform}/" in l and ("_full" in l or "_smart" in l)])
            for f in folders:
                print(f"  • {f}")
    print()

def main():
    if len(sys.argv) == 1:
        show_status()
        print("""Usage:
  os_backup.py --android         Android smart (main folders)
  os_backup.py --android-full    Android full (all data)
  os_backup.py --windows         Windows smart (user data)
  os_backup.py --windows-full    Windows full (entire partition)
""")
        return

    parser = argparse.ArgumentParser(description="OS Backup Tool")
    parser.add_argument("--android", "-a", action="store_true", help="Backup Android (smart)")
    parser.add_argument("--android-full", "-A", action="store_true", help="Backup Android (full)")
    parser.add_argument("--windows", "-w", action="store_true", help="Backup Windows (smart)")
    parser.add_argument("--windows-full", "-W", action="store_true", help="Backup Windows (full)")
    parser.add_argument("--device", "-d", type=str, help="Device name (default: hostname)")
    args = parser.parse_args()

    TMP.mkdir(parents=True, exist_ok=True)

    if args.android:
        backup_android(mode="smart")
    elif args.android_full:
        backup_android(mode="full")
    elif args.windows:
        backup_windows(mode="smart", device_name=args.device)
    elif args.windows_full:
        backup_windows(mode="full", device_name=args.device)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
