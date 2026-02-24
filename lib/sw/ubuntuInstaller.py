#!/usr/bin/env python3
"""Ubuntu Setup Tool"""
import subprocess, sys, os, time

def run(cmd): return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()
def exe(cmd): print(f"  $ {cmd}"); subprocess.run(cmd, shell=True, check=True)
def confirm(msg):
    if input(f"{msg} (y/n): ").strip().lower() != 'y': sys.exit("Aborted.")
def uuid(part): return run(f"blkid -s UUID -o value {part}")

def list_drives():
    print("\nAvailable drives:\n")
    drives = []
    for line in run("lsblk -d -o NAME,SIZE,MODEL,VENDOR").splitlines()[1:]:
        p = line.split(None, 3)
        if len(p) >= 2 and p[1] != "0B" and not p[0].startswith("loop"):
            print(f"  /dev/{p[0]:8} {p[1]:10} {p[2] if len(p)>2 else ''} {p[3].strip() if len(p)>3 else ''}")
            drives.append(f"/dev/{p[0]}")
    return drives

def select_drive(drives):
    dev = input("\nTarget device: ").strip()
    if dev not in drives: confirm(f"'{dev}' not listed. Continue?")
    return dev

if os.geteuid() != 0: sys.exit("Run as root: sudo python3 ubuntuInstaller.py")

print("""
╔════════════════════════════════════════════════════╗
║             Ubuntu Setup Tool                      ║
╠════════════════════════════════════════════════════╣
║  1. USB Installer                                  ║
║     Creates a drive that installs Ubuntu on a PC   ║
║                                                    ║
║  2. Fresh Portable SSD [BROKEN - DO NOT USE]       ║
║     Installs clean Ubuntu to external drive        ║
║                                                    ║
║  3. Clone Drive to Drive                           ║
║     Bit-for-bit copy from one drive to another     ║
╚════════════════════════════════════════════════════╝
""")

choice = input("Select (1/2/3): ").strip()

# =============================================================================
# OPTION 1: Bootable USB Installer
# =============================================================================
if choice == "1":
    print("\n=== USB Installer ===")
    print("Flashes Ubuntu ISO to drive. Boots to install Ubuntu on other PCs.\n")

    drives = list_drives()
    dev = select_drive(drives)
    confirm(f"DESTROY ALL DATA on {dev}?")

    url = "https://releases.ubuntu.com/25.10/ubuntu-25.10-desktop-amd64.iso"
    iso = os.path.join(os.path.dirname(__file__), "data", "ubuntu.iso")
    os.makedirs(os.path.dirname(iso), exist_ok=True)

    if os.path.exists(iso):
        print(f"Using existing: {iso} ({os.path.getsize(iso)//1024//1024}MB)")
    else:
        confirm("Download ISO?")
        subprocess.run(f"wget -O {iso} {url}", shell=True, check=True)

    confirm(f"Unmount {dev}?"); subprocess.run(f"umount {dev}* 2>/dev/null", shell=True)
    confirm(f"Flash to {dev}?"); subprocess.run(f"dd if={iso} of={dev} bs=4M status=progress conv=fsync", shell=True)
    print("\nDone! Bootable Ubuntu installer created.")

# =============================================================================
# OPTION 2: Fresh Portable SSD (extract from ISO - fast, Secure Boot compatible)
# =============================================================================
elif choice == "2":
    print("\n=== Fresh Portable SSD ===")
    print("BROKEN - Does not boot correctly. Use Option 1 + manual install instead.")
    sys.exit(1)

    drives = list_drives()
    dev = select_drive(drives)
    confirm(f"DESTROY ALL DATA on {dev}?")

    # Reuse ISO from Option 1
    iso = os.path.join(os.path.dirname(__file__), "data", "ubuntu.iso")
    url = "https://releases.ubuntu.com/25.10/ubuntu-25.10-desktop-amd64.iso"
    os.makedirs(os.path.dirname(iso), exist_ok=True)
    if os.path.exists(iso):
        print(f"Using existing: {iso}")
    else:
        confirm("Download ISO?")
        subprocess.run(f"wget -O {iso} {url}", shell=True, check=True)

    MNT, ISO_MNT = "/mnt/target", "/mnt/iso"
    p = dev + ("p" if "nvme" in dev else "")
    efi, root = f"{p}1", f"{p}2"

    # Partition + Format
    confirm("Partition and format?")
    subprocess.run(f"umount {dev}* 2>/dev/null", shell=True)
    exe(f"sgdisk --zap-all {dev}")
    exe(f"sgdisk -n 1:0:+512M -t 1:ef00 -c 1:EFI {dev}")
    exe(f"sgdisk -n 2:0:0 -t 2:8300 -c 2:ROOT {dev}")
    exe("partprobe"); time.sleep(2)
    exe(f"mkfs.vfat -F32 -n EFI {efi}")
    exe(f"mkfs.ext4 -F -L UBUNTU {root}")

    # Mount
    confirm("Mount and extract?")
    subprocess.run(f"umount {MNT}/* {MNT} {ISO_MNT} 2>/dev/null", shell=True)
    os.makedirs(MNT, exist_ok=True); os.makedirs(ISO_MNT, exist_ok=True)
    exe(f"mount {root} {MNT}")
    os.makedirs(f"{MNT}/boot/efi", exist_ok=True)
    exe(f"mount {efi} {MNT}/boot/efi")
    exe(f"mount -o loop {iso} {ISO_MNT}")

    # Extract layered squashfs (Ubuntu 25.10+ uses layers)
    exe(f"unsquashfs -f -d {MNT} {ISO_MNT}/casper/minimal.squashfs")
    exe(f"unsquashfs -f -d {MNT} {ISO_MNT}/casper/minimal.standard.squashfs")
    subprocess.run(f"unsquashfs -f -d {MNT} {ISO_MNT}/casper/minimal.standard.en.squashfs", shell=True)  # lang pack may have hardlink issues

    # Configure fstab
    confirm("Configure system and install bootloader?")
    with open(f"{MNT}/etc/fstab", 'w') as f:
        f.write(f"UUID={uuid(root)} / ext4 errors=remount-ro 0 1\n")
        f.write(f"UUID={uuid(efi)} /boot/efi vfat umask=0077 0 1\n")

    # Bind mounts for chroot
    for d in ["dev", "proc", "sys", "run"]: exe(f"mount --bind /{d} {MNT}/{d}")

    # Install GRUB (uses signed packages from extracted system, --removable for portable boot)
    exe(f"chroot {MNT} grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable {dev}")
    exe(f"chroot {MNT} update-grub")

    # Create user
    exe(f"chroot {MNT} useradd -m -s /bin/bash -G sudo ubuntu")
    exe(f"echo 'ubuntu:ubuntu' | chroot {MNT} chpasswd")

    # Cleanup
    confirm("Unmount and finish?")
    for d in ["run", "sys", "proc", "dev", "boot/efi", ""]: subprocess.run(f"umount {MNT}/{d}", shell=True)
    subprocess.run(f"umount {ISO_MNT}", shell=True)

    print(f"\nDone! Ubuntu 25.10 on {dev}")
    print("Login: ubuntu / ubuntu")

# =============================================================================
# OPTION 3: Clone Drive to Drive (dd)
# =============================================================================
elif choice == "3":
    print("\n=== Clone Drive to Drive ===")
    print("Bit-for-bit copy from source drive to destination drive.")
    print("Source must be an existing bootable Ubuntu drive.")
    print("\nWARNING: Do NOT clone a mounted or in-use drive!")
    print("  - dd copies raw blocks with no file awareness")
    print("  - Files changing mid-copy = filesystem corruption")
    print("  - Unmount source drive first, or boot from live USB to clone safely\n")

    drives = list_drives()
    src = input("\nSource drive (existing Ubuntu): ").strip()
    if src not in drives: confirm(f"'{src}' not listed. Continue?")
    dst = input("Destination drive (will be WIPED): ").strip()
    if dst not in drives: confirm(f"'{dst}' not listed. Continue?")
    if src == dst: sys.exit("Source and destination cannot be the same.")

    confirm(f"WIPE {dst} with clone of {src}? ALL DATA ON {dst} DESTROYED")

    # Clone with dd
    subprocess.run(f"umount {dst}* 2>/dev/null", shell=True)
    exe(f"dd if={src} of={dst} bs=64M status=progress conv=fsync")

    # Reload partition table
    exe(f"partprobe {dst}"); time.sleep(3)

    # =========================================================================
    # EXPERIMENTAL - AUTO RESIZE (DISABLED - DO NOT ENABLE WITHOUT TESTING)
    # =========================================================================
    # If destination is larger than source, the extra space is unallocated.
    # The following UNTESTED code attempts to expand the root partition:
    #
    # if confirm("Destination larger than source. Expand root partition?"):
    #     # Fix GPT backup header location (required after dd to larger disk)
    #     exe(f"sgdisk -e {dst}")
    #     # Extend partition 2 (root) to fill remaining space
    #     exe(f"parted {dst} resizepart 2 100%")
    #     # Check and resize ext4 filesystem
    #     p = dst + ("p" if "nvme" in dst else "")
    #     exe(f"e2fsck -f {p}2")
    #     exe(f"resize2fs {p}2")
    #
    # =========================================================================
    # MANUAL RESIZE WITH GPARTED (RECOMMENDED):
    # =========================================================================
    # 1. Boot from USB installer (Option 1) or any Ubuntu live USB
    # 2. Open GParted (search in apps or run: sudo gparted)
    # 3. Select the cloned drive (e.g., /dev/sdf)
    # 4. Right-click the root partition (usually partition 2) → Resize/Move
    # 5. Drag the right edge to fill unallocated space → Resize
    # 6. Click the green checkmark to apply
    # 7. Reboot into the cloned drive
    # =========================================================================

    print(f"\nDone! {dst} is now a clone of {src}")
    print("Boot from the new drive to verify.")
    print("\nNOTE: If destination is larger than source, extra space is unallocated.")
    print("Use GParted from a live USB to expand the root partition (see script comments).")

else:
    sys.exit("Invalid option.")
