"""a sw - Software manager (build, install, update system packages)"""
import sys, os

SW_DIR = os.path.dirname(os.path.abspath(__file__))

SUBCMDS = {
    "update":    ("update.py",               "System updates (apt, npm, conda, etc.)"),
    "clang":     ("clang_installer.py",       "Build Clang/LLVM from source"),
    "tmux":      ("tmux_installer.py",        "Build tmux from source"),
    "alacritty": ("alacritty_installer.py",   "Build Alacritty from source"),
    "foot":      ("foot_installer.py",        "Build foot from source"),
    "ptyxis":    ("ptyxis_installer.py",      "Build Ptyxis from source"),
    "neovim":    ("neovim_installer.py",      "Build Neovim from source"),
    "vscode":    ("vscode_manager.py",        "VS Code installer"),
    "android-studio": ("android_studio_updater.py", "Android Studio updater"),
    "rclone":    ("rclone.py",                "Rclone Google Drive manager"),
    "backup":    ("os_backup.py",             "OS backup (Android/Windows/Linux)"),
    "webstore":  ("webstore.py",              "Chrome extension manager"),
    "mamba":     ("mamba_manager.py",         "Mamba/micromamba manager"),
    "calibre":   ("calibre_manager.py",       "Calibre e-book manager"),
    "waydroid":  ("waydroid_manager.py",      "Waydroid container manager"),
    "android":   ("android_manager.py",       "Android device manager"),
    "dash":      ("dash_to_panel_manager.py", "Dash to Panel config"),
    "disk":      ("disk_speed_test.py",       "Disk speed test"),
    "ssd":       ("ssd_info.py",              "SSD info"),
    "flops":     ("flops_bench.py",           "FLOPS benchmark"),
    "clone":     ("clone_to_drive.py",        "Clone to external drive"),
    "migrate":   ("migrationManager.py",      "Migration manager"),
    "ubuntu":    ("ubuntuInstaller.py",       "Ubuntu fresh install"),
    "android-beta": ("android_beta.py",       "Android beta enrollment"),
}

sub = sys.argv[2] if len(sys.argv) > 2 else None

if not sub or sub in ("help", "-h", "--help"):
    print("a sw - Software manager\n")
    for name, (_, desc) in SUBCMDS.items():
        print(f"  a sw {name:20s} {desc}")
    sys.exit(0)

if sub not in SUBCMDS:
    print(f"Unknown: a sw {sub}")
    print(f"Available: {', '.join(SUBCMDS)}")
    sys.exit(1)

script = os.path.join(SW_DIR, SUBCMDS[sub][0])
os.execvp(sys.executable, [sys.executable, script] + sys.argv[3:])
