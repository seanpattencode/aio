#!/usr/bin/env python3
"""Alacritty Installer - builds GPU-accelerated terminal from source.

Builds latest Alacritty from GitHub. Installs as 'alacritty-source' alongside
the system apt version so both can coexist.
  - Binary: /usr/local/bin/alacritty-source
  - System apt version stays at /usr/bin/alacritty (unchanged)
"""
import subprocess, os, shutil, sys, re
from pathlib import Path

BUILD_DIR = Path.home() / "alacritty-build"
INSTALL_PREFIX = "/usr/local"
BIN_PATH = f"{INSTALL_PREFIX}/bin/alacritty-source"
DESKTOP_FILE = f"{INSTALL_PREFIX}/share/applications/alacritty-source.desktop"
ICON_NAME = "Alacritty-Source"

# Rust perf-max: native + full LTO + single codegen unit (max optimization, slower compile)
RUSTFLAGS = "-C target-cpu=native -C lto=fat -C codegen-units=1 -C opt-level=3 -C link-arg=-fuse-ld=lld"

def _system_path():
    """Return PATH with system dirs first, avoiding conda/micromamba linker conflicts."""
    sys_dirs = ["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"]
    cargo_bin = Path.home() / ".cargo/bin"
    if cargo_bin.exists():
        sys_dirs.append(str(cargo_bin))
    # Append remaining PATH entries that aren't already included
    for p in os.environ.get("PATH", "").split(":"):
        if p and p not in sys_dirs:
            sys_dirs.append(p)
    return ":".join(sys_dirs)

def run(cmd, cwd=None, check=True, system_linker=False):
    print(f">>> {cmd}")
    env = None
    inp = None
    if cmd.strip().startswith("sudo ") and (pw := os.environ.get("SUDO_PW")):
        cmd = cmd.replace("sudo ", "sudo -S ", 1)
        inp = pw
    if system_linker:
        env = {**os.environ, "PATH": _system_path(), "RUSTFLAGS": RUSTFLAGS}
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check, input=inp, text=True if inp else None, env=env)

def get_version():
    r = subprocess.run(f"{BIN_PATH} --version", shell=True, capture_output=True, text=True)
    m = re.search(r'alacritty ([\d.]+)', r.stdout)
    return m.group(1) if m else None

def setup_desktop():
    """Install desktop file and icon so GNOME search finds it."""
    src_desktop = BUILD_DIR / "extra/linux/Alacritty.desktop"
    src_icon = BUILD_DIR / "extra/logo/alacritty-term.svg"
    if not src_desktop.exists():
        print("Desktop file not found in source tree"); return False
    # Write modified desktop file
    content = src_desktop.read_text()
    content = content.replace("Name=Alacritty", "Name=Alacritty (Source)")
    content = content.replace("Exec=alacritty", f"Exec={BIN_PATH}")
    content = content.replace("TryExec=alacritty", f"TryExec={BIN_PATH}")
    content = content.replace("Icon=Alacritty", f"Icon={ICON_NAME}")
    tmp = Path("/tmp/alacritty-source.desktop")
    tmp.write_text(content)
    run(f"sudo cp {tmp} {DESKTOP_FILE}")
    # Install icon
    if src_icon.exists():
        icon_dir = f"{INSTALL_PREFIX}/share/icons/hicolor/scalable/apps"
        run(f"sudo mkdir -p {icon_dir}")
        run(f"sudo cp {src_icon} {icon_dir}/{ICON_NAME}.svg")
        run("sudo gtk-update-icon-cache -f /usr/local/share/icons/hicolor", check=False)
    run("sudo update-desktop-database /usr/local/share/applications", check=False)
    return True

def try_incremental():
    """Try incremental build. Returns True if successful, False to trigger full build."""
    if not (BUILD_DIR / ".git").exists() or not (BUILD_DIR / "target").exists():
        return False
    print("=== Trying incremental build ===\n")
    try:
        run("git fetch --depth 1 origin", cwd=BUILD_DIR)
        # Get latest release tag
        run("git fetch --tags --force", cwd=BUILD_DIR)
        r = subprocess.run("git tag -l 'v*' --sort=-version:refname | head -1", shell=True, cwd=BUILD_DIR, capture_output=True, text=True)
        latest_tag = r.stdout.strip()
        if not latest_tag:
            return False
        # Check if already on this tag
        current = subprocess.run("git describe --tags --exact-match HEAD 2>/dev/null", shell=True, cwd=BUILD_DIR, capture_output=True, text=True)
        if current.stdout.strip() == latest_tag:
            print(f"Already at {latest_tag}.")
            if not Path(DESKTOP_FILE).exists(): setup_desktop()
            return True
        print(f"Updating to {latest_tag}...")
        run(f"git checkout {latest_tag}", cwd=BUILD_DIR)
        run("cargo build --release", cwd=BUILD_DIR, system_linker=True)
        run(f"sudo cp target/release/alacritty {BIN_PATH}", cwd=BUILD_DIR)
        setup_desktop()
        return True
    except Exception as e:
        print(f"Incremental build failed: {e}\nFalling back to full build...\n")
        return False

def install():
    print("=== Alacritty (Source) Installer ===\n")
    # Try incremental first
    if try_incremental():
        if v := get_version(): print(f"\n✓ Updated: alacritty {v}"); return True
    # Dependencies
    if shutil.which("apt"):
        run("sudo apt update", check=False)
        run("sudo apt install -y cmake g++ pkg-config libfreetype-dev libfontconfig-dev libxcb-xfixes0-dev libxkbcommon-dev python3 git")
    elif shutil.which("dnf"):
        run("sudo dnf install -y cmake gcc-c++ freetype-devel fontconfig-devel libxcb-devel libxkbcommon-devel git")
    elif shutil.which("pacman"):
        run("sudo pacman -S --noconfirm cmake freetype2 fontconfig pkg-config make libxcb libxkbcommon python git")
    else:
        print("Unknown package manager"); return False
    # Full clean build
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    run(f"git clone https://github.com/alacritty/alacritty.git {BUILD_DIR}")
    # Checkout latest release tag
    r = subprocess.run("git tag -l 'v*' --sort=-version:refname | head -1", shell=True, cwd=BUILD_DIR, capture_output=True, text=True)
    latest_tag = r.stdout.strip()
    if latest_tag:
        print(f"Building {latest_tag}...")
        run(f"git checkout {latest_tag}", cwd=BUILD_DIR)
    run("cargo build --release", cwd=BUILD_DIR, system_linker=True)
    # Install binary + desktop integration
    run(f"sudo cp target/release/alacritty {BIN_PATH}", cwd=BUILD_DIR)
    setup_desktop()
    # Verify
    if v := get_version():
        sys_ver = subprocess.run("alacritty --version", shell=True, capture_output=True, text=True).stdout.strip()
        print(f"\n✓ Installed: alacritty {v}")
        print(f"  Binary: {BIN_PATH}")
        print(f"  System: {sys_ver}")
        print(f"  Test:   {BIN_PATH}")
        return True
    print("✗ Installation failed"); return False

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install": sys.exit(0 if install() else 1)
    elif cmd in ("-h", "--help", "help"): print(f"Usage: {sys.argv[0]} [install|status]")
    else: print(f"Alacritty (Source): {get_version() or 'not installed'}\n  Binary: {BIN_PATH}\n\nSystem: {subprocess.run('alacritty --version', shell=True, capture_output=True, text=True).stdout.strip() or 'not installed'}\n\nCommands: install, status")
