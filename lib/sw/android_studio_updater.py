#!/usr/bin/env python3
"""Android Studio updater - checks for updates and installs them."""
import subprocess, sys, json, urllib.request, tarfile, shutil, xml.etree.ElementTree as ET
from pathlib import Path

STUDIO_DIR = Path.home() / "Applications" / "android-studio"
RELEASES_URL = "https://jb.gg/android-studio-releases-list.xml"

def get_installed_version():
    """Get installed version from product-info.json (major.minor.patch only)."""
    info = STUDIO_DIR / "product-info.json"
    if not info.exists(): return None
    ver = json.loads(info.read_text())["dataDirectoryName"].replace("AndroidStudio", "")
    return ".".join(ver.split(".")[:3])  # Normalize to major.minor.patch

def get_latest_release():
    """Fetch latest stable release from official XML (returns major.minor.patch only)."""
    with urllib.request.urlopen(RELEASES_URL, timeout=30) as r:
        root = ET.fromstring(r.read())
    for item in root.findall("item"):
        if item.find("channel").text in ("Release", "Patch"):
            ver, url = ".".join(item.find("version").text.split(".")[:3]), None
            for dl in item.findall("download"):
                if dl.find("link").text.endswith("linux.tar.gz"):
                    url = dl.find("link").text
                    break
            return ver, url
    return None, None

def update_studio(url):
    """Download and extract new version."""
    tmp = Path("/tmp/android-studio-update.tar.gz")
    print(f"Downloading {url}...")
    subprocess.run(["curl", "-fSL", "-o", str(tmp), url], check=True)
    print("Extracting...")
    backup = STUDIO_DIR.with_suffix(".bak")
    if STUDIO_DIR.exists():
        shutil.rmtree(backup, ignore_errors=True)
        STUDIO_DIR.rename(backup)
    with tarfile.open(tmp) as t:
        t.extractall(STUDIO_DIR.parent, filter="data")
    tmp.unlink()
    shutil.rmtree(backup, ignore_errors=True)
    print("Update complete!")
    return True

def main():
    installed = get_installed_version()
    print(f"Installed: {installed or 'Not found'}")
    latest, url = get_latest_release()
    print(f"Latest: {latest}")
    if not url:
        return print("Could not find download URL") or 1
    if installed and installed >= latest:
        return print("Already up to date!") or 0
    return 0 if update_studio(url) else 1

if __name__ == "__main__":
    sys.exit(main())
