#!/usr/bin/env python3
"""Ptyxis Installer - builds GTK4 terminal from source.

NOTE: GApplication single-instance conflict
If multiple ptyxis versions are installed (flatpak, apt, source), they share
the same app ID (org.gnome.Ptyxis). Launching one will activate an already-running
instance instead of starting fresh. Solutions:
  1. Uninstall other versions (flatpak, apt) - cleanest
  2. Rebuild with different app ID via meson -Dapp_id=org.gnome.Ptyxis.Source
  3. Manually close other ptyxis before launching source version
"""
import subprocess, os, shutil, sys, re
from pathlib import Path

BUILD_DIR = Path.home() / "ptyxis-build"
INSTALL_PREFIX = "/usr/local"
DESKTOP_FILE = f"{INSTALL_PREFIX}/share/applications/org.gnome.Ptyxis.Source.desktop"
DESKTOP_FILE_ORIG = f"{INSTALL_PREFIX}/share/applications/org.gnome.Ptyxis.desktop"
BIN_PATH = f"{INSTALL_PREFIX}/bin/ptyxis"
ALIAS = "ptyxis-source"

# clang perf-max: O3 + native + LTO + no safety overhead (terminal, not a server)
CFLAGS = "-O3 -march=native -mtune=native -flto -fomit-frame-pointer -fno-stack-protector -fno-common -fvisibility=hidden"
LDFLAGS = "-flto -fuse-ld=lld -Wl,-O2 -Wl,--as-needed -Wl,--gc-sections"

def _system_path():
    """Return PATH with system dirs first, avoiding conda/micromamba linker conflicts."""
    sys_dirs = ["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"]
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
        env = {**os.environ, "PATH": _system_path(), "CC": "clang", "CFLAGS": CFLAGS, "LDFLAGS": LDFLAGS}
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check, input=inp, text=True if inp else None, env=env)

def get_version():
    r = subprocess.run(f"{BIN_PATH} --version", shell=True, capture_output=True, text=True)
    m = re.search(r'Ptyxis ([\d.]+\w*)', r.stdout)
    return m.group(1) if m else None

def check_conflicts():
    """Warn if multiple ptyxis installations detected."""
    conflicts = []
    # Check flatpak
    r = subprocess.run("flatpak list --app | grep -i ptyxis", shell=True, capture_output=True, text=True)
    if r.returncode == 0: conflicts.append(("flatpak", "flatpak uninstall app.devsuite.Ptyxis"))
    # Check apt/system
    if Path("/usr/bin/ptyxis").exists(): conflicts.append(("apt/system", "sudo apt remove ptyxis"))
    if conflicts:
        print("\n⚠️  WARNING: Multiple ptyxis installations detected!")
        print("GApplication single-instance means launching one may activate another.")
        for name, cmd in conflicts:
            print(f"  - {name}: remove with '{cmd}'")
        print()

def setup_desktop():
    """Configure desktop file for GNOME integration."""
    # Handle fresh install (original name) or existing setup
    src = Path(DESKTOP_FILE_ORIG) if Path(DESKTOP_FILE_ORIG).exists() else Path(DESKTOP_FILE)
    if not src.exists(): return False
    # Read and modify desktop file
    content = src.read_text()
    # Set name to "Ptyxis (Source)" - first Name= line only
    content = re.sub(r'^Name=Ptyxis.*$', 'Name=Ptyxis (Source)', content, flags=re.MULTILINE, count=1)
    # Use full path for all Exec lines (handle both relative and already-absolute)
    content = re.sub(r'Exec=(/usr/local/bin/)?ptyxis', f'Exec={BIN_PATH}', content)
    # Disable DBus activation to avoid conflict with system/flatpak versions
    content = content.replace('DBusActivatable=true', 'DBusActivatable=false')
    # Write back
    tmp = Path("/tmp/ptyxis.desktop")
    tmp.write_text(content)
    run(f"sudo cp {tmp} {DESKTOP_FILE}")
    if Path(DESKTOP_FILE_ORIG).exists(): run(f"sudo rm {DESKTOP_FILE_ORIG}")
    run(f"sudo ln -sf {BIN_PATH} /usr/local/bin/{ALIAS}")
    # Update caches
    run("sudo update-desktop-database /usr/local/share/applications", check=False)
    run("sudo gtk-update-icon-cache -f /usr/local/share/icons/hicolor", check=False)
    run("sudo glib-compile-schemas /usr/local/share/glib-2.0/schemas", check=False)
    return True

def try_incremental():
    """Try incremental build. Returns True if successful, False to trigger full build."""
    if not (BUILD_DIR / ".git").exists() or not (BUILD_DIR / "build").exists():
        return False
    print("=== Trying incremental build ===\n")
    try:
        run("git fetch --depth 1 origin", cwd=BUILD_DIR)
        r = subprocess.run("git rev-parse HEAD origin/main", shell=True, cwd=BUILD_DIR, capture_output=True, text=True)
        local, remote = r.stdout.strip().split('\n')
        if local == remote:
            print("Already up to date."); return True
        run("git reset --hard origin/main", cwd=BUILD_DIR)
        run("ninja -C build", cwd=BUILD_DIR, system_linker=True)
        run("sudo ninja -C build install", cwd=BUILD_DIR)
        setup_desktop()
        return True
    except Exception as e:
        print(f"Incremental build failed: {e}\nFalling back to full build...\n")
        return False

def install():
    print("=== Ptyxis (Source) Installer ===\n")
    # Try incremental first
    if try_incremental():
        if v := get_version():
            print(f"\n✓ Updated: Ptyxis {v}")
            check_conflicts()
            return True
    # Dependencies
    if shutil.which("apt"): run("sudo apt update", check=False); run("sudo apt install -y meson ninja-build libgtk-4-dev libadwaita-1-dev libvte-2.91-gtk4-dev libpcre2-dev libjson-glib-dev libportal-gtk4-dev gettext git")
    elif shutil.which("dnf"): run("sudo dnf install -y meson ninja-build gtk4-devel libadwaita-devel vte291-gtk4-devel pcre2-devel json-glib-devel gettext git")
    elif shutil.which("pacman"): run("sudo pacman -S --noconfirm meson ninja gtk4 libadwaita vte4 pcre2 json-glib gettext git")
    else: print("Unknown package manager"); return False
    # Full clean build
    BUILD_DIR.exists() and shutil.rmtree(BUILD_DIR)
    run(f"git clone --depth 1 https://gitlab.gnome.org/chergert/ptyxis.git {BUILD_DIR}")
    run(f"meson setup build --prefix={INSTALL_PREFIX} --buildtype=release", cwd=BUILD_DIR, system_linker=True)
    run("ninja -C build", cwd=BUILD_DIR, system_linker=True)
    run("sudo ninja -C build install", cwd=BUILD_DIR)
    # Setup desktop integration
    setup_desktop()
    # Verify
    if v := get_version():
        print(f"\n✓ Installed: Ptyxis {v}\n  Binary: {BIN_PATH}\n  Alias: {ALIAS}\n  Desktop: Ptyxis (Source)")
        check_conflicts()
        return True
    print("✗ Installation failed"); return False

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install": sys.exit(0 if install() else 1)
    elif cmd == "setup": sys.exit(0 if setup_desktop() else 1)
    elif cmd in ("-h", "--help", "help"): print(f"Usage: {sys.argv[0]} [install|setup|status]")
    else: print(f"Ptyxis (Source): {get_version() or 'not installed'}\n  Binary: {BIN_PATH}\n  Alias: {ALIAS}\n\nCommands: install, setup, status")
