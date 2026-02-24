#!/usr/bin/env python3
"""
Dash-to-Panel Manager
Manages GNOME dash-to-panel extension settings, particularly for multi-monitor setups.
Detects connected monitors and ensures taskbar centering is configured for all displays.

Issue: dash-to-panel stores per-monitor configs by unique ID (Vendor-Serial). When monitors
change, new ones lack config in panel-element-positions and default to left-aligned taskbars.
"""

import subprocess
import sys
import json
import re
import argparse
from typing import Optional


def run_command(cmd: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=capture,
        text=True
    )


def get_connected_monitors() -> list[dict]:
    """
    Get currently connected monitors via Mutter DBus interface.
    Returns list of dicts with connector, vendor, product, serial, and monitor_id.
    """
    result = run_command(
        "gdbus call --session --dest org.gnome.Mutter.DisplayConfig "
        "--object-path /org/gnome/Mutter/DisplayConfig "
        "--method org.gnome.Mutter.DisplayConfig.GetCurrentState"
    )

    if result.returncode != 0:
        print(f"Error querying Mutter: {result.stderr}", file=sys.stderr)
        return []

    monitors = []
    data = result.stdout

    # Parse the Mutter output to extract monitor info
    # Pattern matches: 'connector', 'vendor', 'product', 'serial' sequences
    pattern = r"'(DP-\d+|HDMI-\d+|eDP-\d+|VGA-\d+)'[^']*'([^']+)'[^']*'([^']+)'[^']*'([^']*)'"
    matches = re.findall(pattern, data)

    seen = set()
    for match in matches:
        connector, vendor, product, serial = match
        # Dash-to-panel uses Vendor-Serial format for monitor IDs
        if serial and serial != "0x00000000":
            monitor_id = f"{vendor}-{serial}"
        else:
            monitor_id = f"{vendor}-{product}"

        # Deduplicate (Mutter can report same monitor multiple times)
        if monitor_id not in seen:
            seen.add(monitor_id)
            monitors.append({
                "connector": connector,
                "vendor": vendor,
                "product": product,
                "serial": serial,
                "monitor_id": monitor_id
            })

    return monitors


def get_dconf_setting(key: str) -> Optional[str]:
    """Read a dconf setting value."""
    result = run_command(f"dconf read /org/gnome/shell/extensions/dash-to-panel/{key}")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def set_dconf_setting(key: str, value: str) -> bool:
    """Write a dconf setting value using subprocess to avoid shell escaping issues."""
    try:
        result = subprocess.run(
            ["dconf", "write", f"/org/gnome/shell/extensions/dash-to-panel/{key}", value],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"dconf error: {result.stderr}", file=sys.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Error setting dconf: {e}", file=sys.stderr)
        return False


def parse_panel_element_positions() -> dict:
    """Parse the current panel-element-positions setting."""
    raw = get_dconf_setting("panel-element-positions")
    if not raw:
        return {}

    # Remove outer quotes if present
    raw = raw.strip("'\"")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error parsing panel-element-positions: {e}", file=sys.stderr)
        return {}


def parse_panel_anchors() -> dict:
    """Parse the current panel-anchors setting."""
    raw = get_dconf_setting("panel-anchors")
    if not raw:
        return {}

    raw = raw.strip("'\"")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error parsing panel-anchors: {e}", file=sys.stderr)
        return {}


def get_centered_taskbar_config() -> list[dict]:
    """Return the standard centered taskbar element configuration."""
    return [
        {"element": "showAppsButton", "visible": True, "position": "stackedTL"},
        {"element": "activitiesButton", "visible": False, "position": "stackedTL"},
        {"element": "leftBox", "visible": True, "position": "stackedTL"},
        {"element": "taskbar", "visible": True, "position": "centerMonitor"},
        {"element": "centerBox", "visible": True, "position": "stackedBR"},
        {"element": "rightBox", "visible": True, "position": "stackedBR"},
        {"element": "dateMenu", "visible": True, "position": "stackedBR"},
        {"element": "systemMenu", "visible": True, "position": "stackedBR"},
        {"element": "desktopButton", "visible": True, "position": "stackedBR"}
    ]


def check_status() -> dict:
    """
    Check the current dash-to-panel configuration status.
    Returns dict with connected monitors, configured monitors, and issues found.
    """
    connected = get_connected_monitors()
    positions = parse_panel_element_positions()
    anchors = parse_panel_anchors()

    connected_ids = {m["monitor_id"] for m in connected}
    configured_ids = set(positions.keys())

    missing_config = connected_ids - configured_ids
    orphaned_config = configured_ids - connected_ids

    # Check for non-centered taskbars
    non_centered = []
    for monitor_id, elements in positions.items():
        if monitor_id in connected_ids:
            for elem in elements:
                if elem.get("element") == "taskbar":
                    if elem.get("position") != "centerMonitor":
                        non_centered.append({
                            "monitor_id": monitor_id,
                            "current_position": elem.get("position", "unknown")
                        })

    return {
        "connected_monitors": connected,
        "configured_monitors": list(configured_ids),
        "panel_anchors": anchors,
        "missing_config": list(missing_config),
        "orphaned_config": list(orphaned_config),
        "non_centered_taskbars": non_centered,
        "has_issues": bool(missing_config or non_centered)
    }


def fix_centering(dry_run: bool = False) -> bool:
    """
    Fix taskbar centering for all connected monitors.
    Adds missing monitor configurations and fixes non-centered taskbars.
    Returns True if changes were made (or would be made in dry_run mode).
    """
    status = check_status()

    if not status["has_issues"]:
        print("All monitors have centered taskbar configuration.")
        return False

    positions = parse_panel_element_positions()
    anchors = parse_panel_anchors()
    changes_made = False

    # Add missing monitor configurations
    for monitor_id in status["missing_config"]:
        print(f"Adding centered taskbar config for: {monitor_id}")
        positions[monitor_id] = get_centered_taskbar_config()
        if monitor_id not in anchors:
            anchors[monitor_id] = "MIDDLE"
        changes_made = True

    # Fix non-centered taskbars
    for issue in status["non_centered_taskbars"]:
        monitor_id = issue["monitor_id"]
        print(f"Fixing taskbar position for {monitor_id}: {issue['current_position']} -> centerMonitor")
        for elem in positions.get(monitor_id, []):
            if elem.get("element") == "taskbar":
                elem["position"] = "centerMonitor"
        changes_made = True

    if dry_run:
        print("\n[DRY RUN] Would apply these changes:")
        print(f"  panel-element-positions: {json.dumps(positions)[:100]}...")
        return changes_made

    # Apply changes
    positions_json = json.dumps(positions)
    anchors_json = json.dumps(anchors)

    # dconf expects string values wrapped in double quotes for GVariant
    positions_value = '"' + positions_json.replace('\\', '\\\\').replace('"', '\\"') + '"'
    anchors_value = '"' + anchors_json.replace('\\', '\\\\').replace('"', '\\"') + '"'

    if not set_dconf_setting("panel-element-positions", positions_value):
        print("Error: Failed to set panel-element-positions", file=sys.stderr)
        return False

    if not set_dconf_setting("panel-anchors", anchors_value):
        print("Error: Failed to set panel-anchors", file=sys.stderr)
        return False

    print("Settings updated successfully.")
    return changes_made


def reload_extension() -> bool:
    """Disable and re-enable dash-to-panel to apply changes."""
    print("Reloading dash-to-panel extension...")

    result = run_command("gnome-extensions disable dash-to-panel@jderose9.github.com")
    if result.returncode != 0:
        print(f"Error disabling extension: {result.stderr}", file=sys.stderr)
        return False

    import time
    time.sleep(1)

    result = run_command("gnome-extensions enable dash-to-panel@jderose9.github.com")
    if result.returncode != 0:
        print(f"Error enabling extension: {result.stderr}", file=sys.stderr)
        return False

    print("Extension reloaded successfully.")
    return True


def install_extension() -> bool:
    """Install dash-to-panel from GitHub source."""
    import tempfile
    from pathlib import Path
    ext_dir = Path.home() / ".local/share/gnome-shell/extensions/dash-to-panel@jderose9.github.com"
    if ext_dir.exists():
        print(f"dash-to-panel already installed at {ext_dir}")
        result = run_command("gnome-extensions list | grep dash-to-panel")
        if result.returncode != 0:
            print("\n" + "="*60)
            print("*** YOU MUST LOG OUT AND LOG BACK IN ***")
            print("The extension is installed but GNOME Shell hasn't detected it.")
            print("On Wayland, a logout/login is required for new extensions.")
            print("="*60)
            run_command("gsettings set org.gnome.shell enabled-extensions \"['dash-to-panel@jderose9.github.com']\"")
        return True
    print("Installing dash-to-panel from GitHub...")
    with tempfile.TemporaryDirectory() as tmp:
        result = run_command(f"cd {tmp} && git clone --depth 1 https://github.com/home-sweet-gnome/dash-to-panel.git && cd dash-to-panel && make install")
        if result.returncode != 0:
            print(f"Install failed: {result.stderr}", file=sys.stderr)
            return False
    run_command("gsettings set org.gnome.shell enabled-extensions \"['dash-to-panel@jderose9.github.com']\"")
    print("\n" + "="*60)
    print("*** YOU MUST LOG OUT AND LOG BACK IN ***")
    print("dash-to-panel installed successfully!")
    print("On Wayland, a logout/login is required for new extensions.")
    print("After logging back in, run this script again to configure.")
    print("="*60)
    return True

def print_status(status: dict) -> None:
    """Print a formatted status report."""
    print("\n" + "=" * 60)
    print("Dash-to-Panel Monitor Configuration Status")
    print("=" * 60)

    print("\nConnected Monitors:")
    for m in status["connected_monitors"]:
        anchor = status["panel_anchors"].get(m["monitor_id"], "NOT SET")
        configured = "YES" if m["monitor_id"] in status["configured_monitors"] else "NO"
        print(f"  {m['connector']:8} {m['monitor_id']}")
        print(f"           Vendor: {m['vendor']}, Product: {m['product']}")
        print(f"           Panel config: {configured}, Anchor: {anchor}")

    if status["missing_config"]:
        print(f"\nMissing Configuration (will have left-aligned taskbar):")
        for mid in status["missing_config"]:
            print(f"  - {mid}")

    if status["non_centered_taskbars"]:
        print(f"\nNon-Centered Taskbars:")
        for issue in status["non_centered_taskbars"]:
            print(f"  - {issue['monitor_id']}: position={issue['current_position']}")

    if status["orphaned_config"]:
        print(f"\nOrphaned Configurations (disconnected monitors):")
        for mid in status["orphaned_config"]:
            print(f"  - {mid}")

    print("\n" + "-" * 60)
    if status["has_issues"]:
        print("STATUS: Issues found - run with --fix to correct")
    else:
        print("STATUS: All monitors configured correctly")
    print("-" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Manage dash-to-panel settings for multi-monitor setups",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s install            # Install dash-to-panel from GitHub
  %(prog)s                    # Check current status
  %(prog)s --fix              # Fix centering issues and reload
  %(prog)s --fix --no-reload  # Fix without reloading extension
  %(prog)s --dry-run          # Show what would be changed

Common issues this tool fixes:
  - Missing panel-element-positions for newly connected monitors
  - Taskbars showing on left instead of center
  - Panel anchor misconfigurations
"""
    )
    parser.add_argument("command", nargs="?", default="status", help="Command: install, status (default)")
    parser.add_argument("--fix", action="store_true", help="Fix any centering issues found")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without making changes")
    parser.add_argument("--no-reload", action="store_true", help="Don't reload the extension after fixing")
    parser.add_argument("--json", action="store_true", help="Output status as JSON")

    args = parser.parse_args()

    if args.command == "install":
        return 0 if install_extension() else 1

    # Check if dash-to-panel is installed and enabled
    result = run_command("gnome-extensions list --enabled | grep dash-to-panel")
    if result.returncode != 0:
        print("dash-to-panel not found or not enabled. Run: python dash_to_panel_manager.py install", file=sys.stderr)
        return 1

    status = check_status()

    if args.json:
        print(json.dumps(status, indent=2))
        return 0 if not status["has_issues"] else 1

    print_status(status)

    if args.fix or args.dry_run:
        changes = fix_centering(dry_run=args.dry_run)
        if changes and not args.dry_run and not args.no_reload:
            reload_extension()
            # Verify fix worked
            new_status = check_status()
            if new_status["has_issues"]:
                print("\nWarning: Some issues may still remain.", file=sys.stderr)
                return 1
            print("\nAll issues resolved successfully.")
        elif not changes:
            print("No changes needed.")
        return 0

    return 0 if not status["has_issues"] else 1


if __name__ == "__main__":
    sys.exit(main())
