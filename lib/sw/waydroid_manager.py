#!/usr/bin/env python3
"""Waydroid Manager - Install and run Android in a Linux container.

EXPERIMENTAL: Waydroid may not start on first run. Known issues:
- NVIDIA GPUs require software rendering (auto-configured but may fail)
- First session start can hang - try stopping and starting again
- May need 'reset' then 'init' if it won't start
"""
import subprocess, sys, shutil, os, glob, re

EXPERIMENTAL_WARNING = """
WARNING: Waydroid is EXPERIMENTAL and may not work on first run.
Known issues:
  - NVIDIA GPUs: Often fails, requires software rendering
  - First run: Session may not start, try stop then start again
  - If stuck: Run 'reset' then 'init' to reinitialize
"""

WAYDROID_CFG = "/var/lib/waydroid/waydroid.cfg"
WAYDROID_DATA_DIRS = [
    "/var/lib/waydroid",
    os.path.expanduser("~/.local/share/waydroid"),
    os.path.expanduser("~/.share/waydroid"),
    os.path.expanduser("~/waydroid"),
    os.path.expanduser("~/.waydroid"),
]

def run(cmd, check=True, capture=False, env=None):
    print(f">>> {cmd}", flush=True)
    return subprocess.run(cmd, shell=True, check=check, capture_output=capture, text=True, env=env)

def container_running():
    return subprocess.run("systemctl is-active waydroid-container.service", shell=True, capture_output=True).returncode == 0

def session_running():
    result = subprocess.run("waydroid status", shell=True, capture_output=True, text=True)
    return "RUNNING" in result.stdout

def is_installed():
    return shutil.which("waydroid") is not None

def is_initialized():
    return os.path.exists(WAYDROID_CFG)

def get_gpus():
    """Detect available GPUs and their render nodes."""
    gpus = []
    try:
        # Find all render nodes
        render_nodes = sorted(glob.glob("/dev/dri/renderD*"))
        for node in render_nodes:
            # Try to get GPU info from sysfs
            card_num = node.replace("/dev/dri/renderD", "")
            card_path = f"/sys/class/drm/renderD{card_num}/device"
            vendor = "Unknown"
            try:
                with open(f"{card_path}/vendor", "r") as f:
                    vendor_id = f.read().strip()
                    vendor = {"0x8086": "Intel", "0x1002": "AMD", "0x10de": "NVIDIA"}.get(vendor_id, vendor_id)
            except: pass
            gpus.append({"node": node, "vendor": vendor})
    except Exception as e:
        print(f"Warning: Could not detect GPUs: {e}")
    return gpus

def is_nvidia_primary():
    """Check if NVIDIA is the primary/only GPU."""
    gpus = get_gpus()
    return len(gpus) == 1 and gpus[0]["vendor"] == "NVIDIA"

def install():
    if is_installed():
        print("Waydroid already installed.")
        return True
    print("\n=== Installing Waydroid ===")
    run("sudo apt install curl ca-certificates -y")
    run("curl -s https://repo.waydro.id | sudo bash")
    run("sudo apt install waydroid -y")
    return True

def init(gapps=False, force=False):
    if not is_installed():
        print("Waydroid not installed. Run 'install' first.")
        return False
    if is_initialized() and not force:
        print("Waydroid already initialized. Use 'init-force' to reinitialize.")
        return True

    cmd = "sudo waydroid init"
    if force:
        cmd += " -f"
    if gapps:
        cmd += " -s GAPPS"
    run(cmd)

    # Configure for NVIDIA if needed
    if is_nvidia_primary():
        print("\nNVIDIA GPU detected - configuring software rendering...")
        configure_software_rendering()

    return True

def configure_software_rendering():
    """Configure Waydroid for software rendering (required for NVIDIA)."""
    if not os.path.exists(WAYDROID_CFG):
        print("Config not found. Run init first.")
        return False

    # Read current config
    with open(WAYDROID_CFG, "r") as f:
        config = f.read()

    # Check if already configured
    if "ro.hardware.egl=swiftshader" in config:
        print("Software rendering already configured.")
        return True

    # Add properties if [properties] section exists
    if "[properties]" in config:
        config = config.replace("[properties]",
            "[properties]\nro.hardware.gralloc=default\nro.hardware.egl=swiftshader")
    else:
        config += "\n[properties]\nro.hardware.gralloc=default\nro.hardware.egl=swiftshader\n"

    # Write config
    run(f"sudo tee {WAYDROID_CFG} > /dev/null << 'EOF'\n{config}\nEOF")
    run("sudo waydroid upgrade --offline", check=False)
    print("Software rendering configured.")
    return True

def configure_gpu(gpu_node):
    """Configure Waydroid to use a specific GPU render node."""
    if not os.path.exists(WAYDROID_CFG):
        print("Config not found. Run init first.")
        return False

    config_nodes = "/var/lib/waydroid/lxc/waydroid/config_nodes"
    if os.path.exists(config_nodes):
        run(f"sudo sed -i 's|/dev/dri/renderD[0-9]*|{gpu_node}|g' {config_nodes}", check=False)

    print(f"GPU configured to use: {gpu_node}")
    return True

def list_gpus():
    """List available GPUs."""
    gpus = get_gpus()
    if not gpus:
        print("No GPUs detected.")
        return False
    print("\nAvailable GPUs:")
    for i, gpu in enumerate(gpus):
        print(f"  {i+1}. {gpu['vendor']} - {gpu['node']}")
    print("\nTo select a GPU: python3 waydroid_manager.py select-gpu <number>")
    return True

def select_gpu(num):
    """Select which GPU to use for Waydroid."""
    gpus = get_gpus()
    if not gpus:
        print("No GPUs detected.")
        return False
    if num < 1 or num > len(gpus):
        print(f"Invalid selection. Choose 1-{len(gpus)}")
        return False

    gpu = gpus[num - 1]
    print(f"Selecting: {gpu['vendor']} - {gpu['node']}")

    if gpu["vendor"] == "NVIDIA":
        print("NVIDIA GPU selected - configuring software rendering...")
        configure_software_rendering()
    else:
        configure_gpu(gpu["node"])

    print("GPU configured. Restart waydroid session to apply.")
    return True

def start():
    """Start session in background and launch UI."""
    if not is_installed():
        print("Waydroid not installed.")
        return False
    if not is_initialized():
        print("Waydroid not initialized. Run 'init' first.")
        return False
    print("NOTE: First run may fail. If it hangs, Ctrl+C and try 'stop' then 'start' again.")

    # Start container service
    if not container_running():
        run("sudo systemctl start waydroid-container.service")

    # Start session in background if not running
    if not session_running():
        print("Starting session in background...", flush=True)
        subprocess.Popen(
            "waydroid session start",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # Wait for session to start
        import time
        for i in range(30):
            time.sleep(1)
            if session_running():
                print("Session started.")
                break
            print(".", end="", flush=True)
        else:
            print("\nSession failed to start. Check 'waydroid log' for details.")
            return False
        print()
    else:
        print("Session already running.")

    # Launch UI
    print("Launching UI...")
    run("waydroid show-full-ui", check=False)
    return True

def session_only():
    """Start session blocking (for running in separate terminal)."""
    if not is_installed():
        print("Waydroid not installed.")
        return False
    if not is_initialized():
        print("Waydroid not initialized. Run 'init' first.")
        return False

    if not container_running():
        run("sudo systemctl start waydroid-container.service")

    print("Starting session (Ctrl+C to stop)...", flush=True)
    try:
        run("waydroid session start")
    except KeyboardInterrupt:
        print("\nSession stopped.")
    return True

def ui():
    """Launch UI (session must be running)."""
    if not is_installed():
        print("Waydroid not installed.")
        return False
    if not session_running():
        print("Session not running. Use 'start' to start session and UI together.")
        return False
    run("waydroid show-full-ui", check=False)
    return True

def stop():
    run("waydroid session stop", check=False)
    run("sudo systemctl stop waydroid-container.service", check=False)
    print("Waydroid stopped.")
    return True

def configure_multiwindow(enable=True):
    """Enable or disable multi-window mode."""
    if not session_running():
        print("Session must be running to configure properties.")
        print("Run 'start' first, then in another terminal run this command.")
        return False

    value = "true" if enable else "false"
    run(f"waydroid prop set persist.waydroid.multi_windows {value}", check=False)
    run("waydroid prop set persist.waydroid.cursor_on_subsurface false", check=False)
    print(f"Multi-window mode {'enabled' if enable else 'disabled'}.")
    print("Restart session for changes to take effect: stop, then start")
    return True

def status():
    print("\n=== Waydroid Status ===")
    print(f"Installed: {is_installed()}")
    print(f"Initialized: {is_initialized()}")
    print(f"Container running: {container_running()}")
    print(f"Session running: {session_running()}")

    if is_installed():
        print("\n--- waydroid status ---")
        run("waydroid status", check=False)

    print("\n--- Available GPUs ---")
    list_gpus()
    return True

def logs():
    """Show waydroid logs."""
    run("waydroid log", check=False)
    return True

def reset():
    """Full cleanup and reset of Waydroid."""
    print("This will remove all Waydroid data and require reinitialization.")
    confirm = input("Continue? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return False

    print("\n=== Resetting Waydroid ===")
    stop()

    # Remove application shortcuts
    run("rm -f ~/.local/share/applications/*aydroid*", check=False)

    # Remove data directories
    for d in WAYDROID_DATA_DIRS:
        if os.path.exists(d):
            print(f"Removing {d}")
            run(f"sudo rm -rf {d}", check=False)

    print("\nReset complete. Run 'init' to reinitialize.")
    return True

def shell():
    """Open Android shell."""
    if not session_running():
        print("Session not running. Start it first.")
        return False
    run("sudo waydroid shell", check=False)
    return True

def install_apk(apk_path):
    """Install an APK file."""
    if not session_running():
        print("Session not running. Start it first.")
        return False
    if not os.path.exists(apk_path):
        print(f"APK not found: {apk_path}")
        return False
    run(f"waydroid app install {apk_path}")
    return True

CMDS = {
    "install":      ("Install Waydroid", install),
    "init":         ("Initialize (download Android image)", lambda: init(False)),
    "init-gapps":   ("Initialize with Google Play", lambda: init(True)),
    "init-force":   ("Force reinitialize", lambda: init(False, True)),
    "start":        ("Start session + UI", start),
    "session":      ("Start session only (blocking)", session_only),
    "ui":           ("Launch UI (session must be running)", ui),
    "stop":         ("Stop session and container", stop),
    "status":       ("Show status", status),
    "logs":         ("Show logs", logs),
    "shell":        ("Open Android shell", shell),
    "multiwindow":  ("Enable multi-window mode (session must be running)", lambda: configure_multiwindow(True)),
    "fullscreen":   ("Disable multi-window mode", lambda: configure_multiwindow(False)),
    "gpus":         ("List available GPUs", list_gpus),
    "select-gpu":   ("Select GPU (requires number argument)", None),
    "software-gpu": ("Configure software rendering (for NVIDIA)", configure_software_rendering),
    "reset":        ("Full reset (removes all data)", reset),
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print("Waydroid Manager - Run Android apps on Linux")
        print(EXPERIMENTAL_WARNING)
        print("Commands:")
        for c, (d, _) in CMDS.items():
            print(f"  {c:14} - {d}")
        print("\nTypical flow:")
        print("  1. install        - Install waydroid package")
        print("  2. init           - Download Android image")
        print("  3. start          - Start session and launch UI")
        print("  4. multiwindow    - (optional) Enable multi-window mode")
        print("\nTroubleshooting:")
        print("  - Black screen? Try: gpus, then select-gpu <n>")
        print("  - NVIDIA GPU? Run: software-gpu")
        print("  - Still broken? Run: reset, then init")
        return 0

    cmd = sys.argv[1]

    # Handle select-gpu with argument
    if cmd == "select-gpu":
        if len(sys.argv) < 3:
            print("Usage: select-gpu <number>")
            list_gpus()
            return 1
        try:
            return 0 if select_gpu(int(sys.argv[2])) else 1
        except ValueError:
            print("Invalid GPU number")
            return 1

    # Handle install-apk with argument
    if cmd == "install-apk":
        if len(sys.argv) < 3:
            print("Usage: install-apk <path-to-apk>")
            return 1
        return 0 if install_apk(sys.argv[2]) else 1

    if cmd not in CMDS:
        print(f"Unknown command: {cmd}")
        return 1

    func = CMDS[cmd][1]
    if func is None:
        print(f"Command '{cmd}' requires additional arguments. Run with --help")
        return 1

    return 0 if func() else 1

if __name__ == "__main__":
    sys.exit(main())
