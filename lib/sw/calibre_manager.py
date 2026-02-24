#!/usr/bin/env python3
import subprocess, sys, shutil, re
from pathlib import Path
GDRIVE_FOLDER_ID, LIB = "1TH9q2OE42sd6O-SkI_hVzluNeuuFukM7", Path.home() / "CalibreLibrary"

def get_version():
    r = subprocess.run("calibre --version", shell=True, capture_output=True, text=True)
    return (m := re.search(r'calibre (\d+\.\d+\.\d+)', r.stdout)) and m.group(1)

def status():
    v, lib_exists, books = get_version(), LIB.exists(), len(list(LIB.glob("*/"))) if LIB.exists() else 0
    remote = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True).stdout.strip().split('\n')[0] if shutil.which("rclone") else None
    print(f"\n=== Calibre Status ===\nInstalled: {v or 'No'}\nLibrary: {LIB} ({'exists' if lib_exists else 'missing'})\nBooks: {books}\nGDrive remote: {remote or 'Not configured'}\nGDrive folder: {GDRIVE_FOLDER_ID}\n")

def install(): subprocess.run("sudo -v && wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh | sudo sh /dev/stdin", shell=True, check=True); setup_library()

def setup_library():
    LIB.mkdir(exist_ok=True)
    remote = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True).stdout.strip().split('\n')[0]
    subprocess.run(["rclone", "sync", remote, str(LIB), f"--drive-root-folder-id={GDRIVE_FOLDER_ID}", "--progress"], check=True)
    cfg = Path.home() / ".config/calibre/global.py"; cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(f"library_path = '{LIB}'\n"); print(f"Library set to {LIB}")

def sync_to_drive():
    remote = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True).stdout.strip().split('\n')[0]
    subprocess.run(["rclone", "sync", str(LIB), remote, f"--drive-root-folder-id={GDRIVE_FOLDER_ID}", "--progress"], check=True)
    print("Uploaded to Google Drive")

def launch(): subprocess.Popen(["calibre", f"--with-library={LIB}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

CMDS = {"status": ("Show status", status), "install": ("Install Calibre + sync library", install), "setup": ("Sync GDrive library", setup_library),
        "upload": ("Upload library to GDrive", sync_to_drive), "launch": ("Launch Calibre", launch), "uninstall": ("Uninstall Calibre", lambda: subprocess.run("sudo calibre-uninstall", shell=True))}

def menu():
    status()
    print("Options:")
    for i, (k, (desc, _)) in enumerate(CMDS.items(), 1): print(f"  {i}. {k:10} - {desc}")
    print(f"  q. quit\n")
    while (c := input("> ").strip().lower()) != 'q':
        if c.isdigit() and 1 <= int(c) <= len(CMDS): list(CMDS.values())[int(c)-1][1]()
        elif c in CMDS: CMDS[c][1]()
        else: print("Invalid option")
        status()

if __name__ == "__main__":
    if len(sys.argv) > 1: CMDS.get(sys.argv[1], (None, lambda: print(f"Unknown: {sys.argv[1]}")))[1]()
    else: menu()
