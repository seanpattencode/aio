#!/usr/bin/env python3
"""
Drive Clone Script - Interactive Version
Clones current Ubuntu system to a new drive with custom partitioning.

PARTITION LAYOUT:
  1. Sync Partition (exFAT) - FIRST because Android/Windows/macOS can discover it
     as the primary visible partition when the drive is connected to other devices.
  2. EFI System Partition (FAT32) - Bootloader
  3. Root Partition (ext4) - Ubuntu system
"""
import subprocess
import sys
import os
import time

# Default Configuration
CONFIG = {
    "target_drive": "/dev/sdf",
    "sync_size_mb": 200 * 1024,  # 200 GB
    "sync_label": "TRANS_4TB",
    "sync_fs": "exfat",
    "efi_size_mb": 512,
    "efi_label": "EFI",
    "root_label": "AIOS_ROOT",
    "mount_root": "/mnt/target_root",
    "mount_efi": "/mnt/target_efi",
}

EXCLUDES = [
    "/dev/*", "/proc/*", "/sys/*", "/tmp/*", "/run/*",
    "/mnt/*", "/media/*", "/lost+found", "/swapfile", "/cdrom"
]

def run_cmd(command, shell=False, check=True):
    """Runs a shell command."""
    cmd_str = command if isinstance(command, str) else ' '.join(command)
    print(f"  $ {cmd_str}")
    if check:
        subprocess.run(command, check=True, shell=shell)
    else:
        return subprocess.run(command, shell=shell, capture_output=True, text=True)

def get_uuid(partition):
    """Gets the UUID of a partition."""
    try:
        result = subprocess.check_output(["blkid", "-s", "UUID", "-o", "value", partition])
        return result.decode("utf-8").strip()
    except:
        return None

def ask_permission(step_name, description, params=None):
    """Ask user for permission and optionally modify parameters."""
    print(f"\n{'='*60}")
    print(f"STEP: {step_name}")
    print(f"{'='*60}")
    print(f"\n{description}\n")

    if params:
        print("Current parameters:")
        for key, val in params.items():
            print(f"  [{key}] {val}")
        print()

    while True:
        if params:
            choice = input("(y)es to proceed | (n)o to abort | (c)hange parameter: ").strip().lower()
        else:
            choice = input("(y)es to proceed | (n)o to abort: ").strip().lower()

        if choice == 'y':
            return True, params
        elif choice == 'n':
            print("Aborted by user.")
            sys.exit(0)
        elif choice == 'c' and params:
            param_key = input(f"Enter parameter name to change {list(params.keys())}: ").strip()
            if param_key in params:
                new_val = input(f"New value for '{param_key}' (current: {params[param_key]}): ").strip()
                # Convert to int if original was int
                if isinstance(params[param_key], int):
                    try:
                        new_val = int(new_val)
                    except ValueError:
                        print("Invalid integer, keeping original.")
                        continue
                params[param_key] = new_val
                print(f"Updated: {param_key} = {new_val}")
            else:
                print(f"Unknown parameter: {param_key}")
        else:
            print("Invalid choice.")

def main():
    if os.geteuid() != 0:
        print("This script must be run as root (sudo).")
        sys.exit(1)

    print("""
╔══════════════════════════════════════════════════════════════╗
║   ⚠️  EXPERIMENTAL - NOT TESTED - USE AT YOUR OWN RISK ⚠️    ║
╠══════════════════════════════════════════════════════════════╣
║  This script has NOT been tested on real hardware.           ║
║  It may contain bugs that could result in DATA LOSS.         ║
║                                                               ║
║  You should:                                                  ║
║    - Have full backups of all important data                 ║
║    - Understand exactly what each step does                  ║
║    - Be prepared to recover manually if something fails      ║
╚══════════════════════════════════════════════════════════════╝
    """)

    dismiss = input("Type 'I understand this is experimental' to continue: ").strip()
    if dismiss != "I understand this is experimental":
        print("Aborted. You must acknowledge the experimental status.")
        sys.exit(1)

    print("""
╔══════════════════════════════════════════════════════════════╗
║          DRIVE CLONE SCRIPT - INTERACTIVE MODE               ║
╠══════════════════════════════════════════════════════════════╣
║  This script will:                                           ║
║    1. Wipe and partition a target drive                      ║
║    2. Format partitions                                      ║
║    3. Clone current system via rsync                         ║
║    4. Update fstab and install GRUB                          ║
║                                                               ║
║  NOTE: Sync partition is FIRST so other devices (Android,    ║
║        Windows, macOS) can discover it as the primary        ║
║        visible partition when connected.                     ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # ─────────────────────────────────────────────────────────────
    # STEP 0: Confirm target drive
    # ─────────────────────────────────────────────────────────────
    print("\nAvailable block devices:")
    run_cmd("lsblk -d -o NAME,SIZE,MODEL,TRAN", shell=True, check=False)

    _, params = ask_permission(
        "SELECT TARGET DRIVE",
        "!!! WARNING !!! All data on the target drive will be DESTROYED.\n"
        "Make absolutely sure you select the correct drive.",
        {"target_drive": CONFIG["target_drive"]}
    )
    CONFIG["target_drive"] = params["target_drive"]
    TARGET = CONFIG["target_drive"]

    # ─────────────────────────────────────────────────────────────
    # STEP 1: Partition sizes
    # ─────────────────────────────────────────────────────────────
    _, params = ask_permission(
        "PARTITION LAYOUT",
        "Configure partition sizes.\n"
        "Partition order:\n"
        "  1. Sync (exFAT) - First so other OSes see it as primary\n"
        "  2. EFI (FAT32)  - Boot partition\n"
        "  3. Root (ext4)  - Uses remaining space",
        {
            "sync_size_mb": CONFIG["sync_size_mb"],
            "sync_label": CONFIG["sync_label"],
            "efi_size_mb": CONFIG["efi_size_mb"],
            "root_label": CONFIG["root_label"],
        }
    )
    CONFIG.update(params)

    # ─────────────────────────────────────────────────────────────
    # STEP 2: Final confirmation before destructive operations
    # ─────────────────────────────────────────────────────────────
    ask_permission(
        "FINAL CONFIRMATION",
        f"About to WIPE {TARGET} and create:\n"
        f"  Partition 1: {CONFIG['sync_size_mb']}MB {CONFIG['sync_fs'].upper()} ({CONFIG['sync_label']})\n"
        f"  Partition 2: {CONFIG['efi_size_mb']}MB FAT32 (EFI)\n"
        f"  Partition 3: Remaining space ext4 ({CONFIG['root_label']})\n\n"
        "Type 'y' only if you are CERTAIN this is correct."
    )

    # ─────────────────────────────────────────────────────────────
    # STEP 3: Wipe and partition
    # ─────────────────────────────────────────────────────────────
    ask_permission(
        "WIPE DISK",
        f"This will run: sgdisk --zap-all {TARGET}\n"
        "All existing partitions and data will be destroyed."
    )
    run_cmd(f"sgdisk --zap-all {TARGET}", shell=True)

    ask_permission(
        "CREATE PARTITIONS",
        "Creating GPT partitions:\n"
        f"  1: {CONFIG['sync_size_mb']}MB exFAT (ANDROID_SYNC) - type 0700\n"
        f"  2: {CONFIG['efi_size_mb']}MB FAT32 (EFI_SYSTEM) - type ef00\n"
        f"  3: Remaining ext4 (UBUNTU_ROOT) - type 8300"
    )
    run_cmd(["sgdisk", "-n", f"1:0:+{CONFIG['sync_size_mb']}M", "-c", "1:ANDROID_SYNC", "-t", "1:0700", TARGET])
    run_cmd(["sgdisk", "-n", f"2:0:+{CONFIG['efi_size_mb']}M", "-c", "2:EFI_SYSTEM", "-t", "2:ef00", TARGET])
    run_cmd(["sgdisk", "-n", "3:0:0", "-c", "3:UBUNTU_ROOT", "-t", "3:8300", TARGET])
    run_cmd("partprobe", shell=True)
    time.sleep(2)

    # Partition paths
    p_prefix = TARGET + ("p" if "nvme" in TARGET else "")
    part_sync = f"{p_prefix}1"
    part_efi = f"{p_prefix}2"
    part_root = f"{p_prefix}3"

    # ─────────────────────────────────────────────────────────────
    # STEP 4: Format partitions
    # ─────────────────────────────────────────────────────────────
    ask_permission(
        "FORMAT PARTITIONS",
        f"Will format:\n"
        f"  {part_sync} -> exFAT ({CONFIG['sync_label']})\n"
        f"  {part_efi} -> FAT32 (EFI)\n"
        f"  {part_root} -> ext4 ({CONFIG['root_label']})"
    )
    run_cmd(["mkfs.exfat", "-n", CONFIG["sync_label"], part_sync])
    run_cmd(["mkfs.vfat", "-F32", "-n", CONFIG["efi_label"], part_efi])
    run_cmd(["mkfs.ext4", "-F", "-L", CONFIG["root_label"], part_root])

    # ─────────────────────────────────────────────────────────────
    # STEP 5: Mount partitions
    # ─────────────────────────────────────────────────────────────
    MOUNT_ROOT = CONFIG["mount_root"]

    ask_permission(
        "MOUNT PARTITIONS",
        f"Will mount:\n"
        f"  {part_root} -> {MOUNT_ROOT}\n"
        f"  {part_efi} -> {MOUNT_ROOT}/boot/efi"
    )
    os.makedirs(MOUNT_ROOT, exist_ok=True)
    run_cmd(["mount", part_root, MOUNT_ROOT])
    os.makedirs(f"{MOUNT_ROOT}/boot/efi", exist_ok=True)
    run_cmd(["mount", part_efi, f"{MOUNT_ROOT}/boot/efi"])

    # ─────────────────────────────────────────────────────────────
    # STEP 6: Clone with rsync
    # ─────────────────────────────────────────────────────────────
    exclude_display = '\n    '.join(EXCLUDES)
    ask_permission(
        "CLONE SYSTEM (RSYNC)",
        f"Will run rsync to clone / to {MOUNT_ROOT}\n\n"
        f"Excluded paths:\n    {exclude_display}\n\n"
        "This may take a long time depending on system size."
    )
    exclude_args = []
    for exc in EXCLUDES:
        exclude_args.extend(["--exclude", exc])
    rsync_cmd = ["rsync", "-aAXv", "--info=progress2"] + exclude_args + ["/", MOUNT_ROOT]
    run_cmd(rsync_cmd)

    # ─────────────────────────────────────────────────────────────
    # STEP 7: Update fstab
    # ─────────────────────────────────────────────────────────────
    uuid_root = get_uuid(part_root)
    uuid_efi = get_uuid(part_efi)

    ask_permission(
        "UPDATE FSTAB",
        f"Will update {MOUNT_ROOT}/etc/fstab with new UUIDs:\n"
        f"  Root UUID: {uuid_root}\n"
        f"  EFI UUID:  {uuid_efi}"
    )

    fstab_path = f"{MOUNT_ROOT}/etc/fstab"
    if os.path.exists(fstab_path):
        with open(fstab_path, 'r') as f:
            lines = f.read().splitlines()

        new_lines = []
        for line in lines:
            if " / " in line and not line.strip().startswith("#"):
                new_lines.append(f"# {line} (Original)")
                new_lines.append(f"UUID={uuid_root} / ext4 errors=remount-ro 0 1")
            elif "/boot/efi" in line and not line.strip().startswith("#"):
                new_lines.append(f"# {line} (Original)")
                new_lines.append(f"UUID={uuid_efi} /boot/efi vfat umask=0077 0 1")
            else:
                new_lines.append(line)

        with open(fstab_path, 'w') as f:
            f.write("\n".join(new_lines) + "\n")
        print("  fstab updated.")

    # ─────────────────────────────────────────────────────────────
    # STEP 8: Install GRUB
    # ─────────────────────────────────────────────────────────────
    ask_permission(
        "INSTALL GRUB BOOTLOADER",
        f"Will bind mount /dev, /proc, /sys and run:\n"
        f"  chroot {MOUNT_ROOT} grub-install {TARGET}\n"
        f"  chroot {MOUNT_ROOT} update-grub"
    )

    for folder in ["dev", "proc", "sys"]:
        run_cmd(["mount", "--bind", f"/{folder}", f"{MOUNT_ROOT}/{folder}"])

    try:
        run_cmd(f"chroot {MOUNT_ROOT} grub-install {TARGET}", shell=True)
        run_cmd(f"chroot {MOUNT_ROOT} update-grub", shell=True)
    except Exception as e:
        print(f"  GRUB warning: {e}")
        print("  You may need Boot-Repair later.")

    # ─────────────────────────────────────────────────────────────
    # STEP 9: Cleanup
    # ─────────────────────────────────────────────────────────────
    ask_permission(
        "CLEANUP",
        "Will unmount all partitions:\n"
        f"  {MOUNT_ROOT}/dev\n"
        f"  {MOUNT_ROOT}/proc\n"
        f"  {MOUNT_ROOT}/sys\n"
        f"  {MOUNT_ROOT}/boot/efi\n"
        f"  {MOUNT_ROOT}"
    )

    for path in [f"{MOUNT_ROOT}/dev", f"{MOUNT_ROOT}/proc", f"{MOUNT_ROOT}/sys",
                 f"{MOUNT_ROOT}/boot/efi", MOUNT_ROOT]:
        run_cmd(["umount", path], check=False)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                        SUCCESS!                              ║
╠══════════════════════════════════════════════════════════════╣
║  Partition 1 (Sync):  {part_sync:<38} ║
║  Partition 2 (EFI):   {part_efi:<38} ║
║  Partition 3 (Root):  {part_root:<38} ║
╚══════════════════════════════════════════════════════════════╝

Reboot and select the new drive from BIOS/UEFI boot menu.
    """)

if __name__ == "__main__":
    main()
