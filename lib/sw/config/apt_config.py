"""Per-machine apt configuration.

MODES:
- default: Ubuntu updates only
- fast-stable-kernel: Proposed for all EXCEPT kernel (pinned to updates)
  Requires nvidia-dkms for module building. See docs/dkms-vs-prebuilt.md

ARCHIVED: "fast" mode removed - caused nvidia/kernel module mismatches.
See archive/apt_config_fast_mode.py
"""
import json, socket, subprocess
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
MODES = {
    "default": "sudo apt full-upgrade -y --allow-downgrades",
    "fast-stable-kernel": "sudo apt -o APT::Get::Always-Include-Phased-Updates=true full-upgrade -y --allow-downgrades",
}

def get_machine_name(): return socket.gethostname()
def get_config_path(): return CONFIG_DIR / f"{get_machine_name()}.json"
def load(): return json.loads(get_config_path().read_text()) if get_config_path().exists() else {"mode": "default"}
def save(config): get_config_path().write_text(json.dumps(config, indent=2)); return config
def get_cmd(mode="default"): return MODES.get(mode, MODES["default"])
def get_codename(): return subprocess.run("lsb_release -cs", shell=True, capture_output=True, text=True).stdout.strip()

def check_fast_stable_kernel_setup():
    """Return (is_setup, missing_cmds) for fast-stable-kernel mode."""
    codename = get_codename()
    missing = []

    # Proposed repo
    if not Path(f"/etc/apt/sources.list.d/{codename}-proposed.list").exists():
        missing.append(f'echo "deb http://archive.ubuntu.com/ubuntu {codename}-proposed main restricted universe multiverse" | sudo tee /etc/apt/sources.list.d/{codename}-proposed.list')

    # Disable phased updates
    if not Path("/etc/apt/apt.conf.d/99-phased-updates").exists():
        missing.append('echo \'APT::Get::Always-Include-Phased-Updates "true";\' | sudo tee /etc/apt/apt.conf.d/99-phased-updates')

    # Boost proposed priority
    if not Path("/etc/apt/preferences.d/proposed-boost").exists():
        missing.append(f'echo -e "Package: *\\nPin: release a={codename}-proposed\\nPin-Priority: 600" | sudo tee /etc/apt/preferences.d/proposed-boost')

    # Pin kernel to updates (higher than proposed)
    if not Path("/etc/apt/preferences.d/kernel-stable").exists():
        missing.append(f'echo -e "Package: linux-*\\nPin: release a={codename}-updates\\nPin-Priority: 700" | sudo tee /etc/apt/preferences.d/kernel-stable')

    # Check nvidia-dkms installed (not prebuilt modules)
    result = subprocess.run("dpkg -l nvidia-dkms-580-open 2>/dev/null | grep -q '^ii'", shell=True)
    if result.returncode != 0:
        missing.append("sudo apt install nvidia-dkms-580-open linux-headers-$(uname -r) && sudo apt remove 'linux-modules-nvidia-*'")

    return len(missing) == 0, missing
