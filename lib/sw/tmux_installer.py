#!/usr/bin/env python3
"""Tmux Installer - builds from source with latest features."""
import subprocess, os, shutil, sys
from pathlib import Path

BUILD_DIR = Path.home() / "tmux-build"

def run(cmd, cwd=None, check=True):
    print(f">>> {cmd}")
    if cmd.strip().startswith("sudo ") and (pw := os.environ.get("SUDO_PW")):
        return subprocess.run(cmd.replace("sudo ", "sudo -S ", 1), shell=True, cwd=cwd, check=check, input=pw, text=True)
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check)

def get_version():
    r = subprocess.run("tmux -V", shell=True, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None

def try_incremental():
    """Try incremental build. Returns True if successful, False to trigger full build."""
    if not (BUILD_DIR / ".git").exists() or not (BUILD_DIR / "Makefile").exists():
        return False
    print("=== Trying incremental build ===\n")
    try:
        run("git fetch --depth 1 origin", cwd=BUILD_DIR)
        r = subprocess.run("git rev-parse HEAD origin/master", shell=True, cwd=BUILD_DIR, capture_output=True, text=True)
        local, remote = r.stdout.strip().split('\n')
        if local == remote:
            print("Already up to date."); return True
        run("git reset --hard origin/master", cwd=BUILD_DIR)
        run("make", cwd=BUILD_DIR)
        run("sudo make install", cwd=BUILD_DIR)
        return True
    except Exception as e:
        print(f"Incremental build failed: {e}\nFalling back to full build...\n")
        return False

def install():
    print("=== Tmux Installer ===\n")
    # Try incremental first
    if try_incremental():
        if v := get_version(): print(f"\n✓ Updated: {v}"); return True
    # Dependencies
    if shutil.which("apt"): run("sudo apt update", check=False); run("sudo apt install -y build-essential libevent-dev libncurses-dev bison pkg-config autoconf automake git")
    elif shutil.which("dnf"): run("sudo dnf install -y gcc make libevent-devel ncurses-devel bison pkgconfig autoconf automake git")
    elif shutil.which("pacman"): run("sudo pacman -S --noconfirm base-devel libevent ncurses git")
    elif shutil.which("brew"): run("brew install libevent ncurses automake autoconf pkg-config git")
    else: print("Unknown package manager"); return False
    # Full clean build
    BUILD_DIR.exists() and shutil.rmtree(BUILD_DIR)
    run(f"git clone --depth 1 https://github.com/tmux/tmux.git {BUILD_DIR}")
    run("sh autogen.sh && ./configure && make", cwd=BUILD_DIR)
    run("sudo make install", cwd=BUILD_DIR)
    # Verify
    if v := get_version(): print(f"\n✓ Installed: {v}\nCleanup: rm -rf {BUILD_DIR}"); return True
    print("✗ Installation failed"); return False

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install": sys.exit(0 if install() else 1)
    elif cmd in ("-h", "--help", "help"): print(f"Usage: {sys.argv[0]} [install|status]")
    else: print(f"Tmux: {get_version() or 'not installed'}\n\nTo install/update: {sys.argv[0]} install")
