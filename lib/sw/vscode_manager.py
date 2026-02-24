#!/usr/bin/env python3
import json, os, subprocess, sys

BUILDS = [("code-insiders", "insider", "code"), ("code", "stable", "code-stable")]
SETTINGS = ["~/.config/Code/User/settings.json", "~/.config/Code - Insiders/User/settings.json"]
BASHRC, sudo = os.path.expanduser("~/.bashrc"), lambda c: f"echo '{os.environ.get('SUDO_PW')}' | sudo -S {c}" if os.environ.get("SUDO_PW") else f"sudo {c}"

def install():
    subprocess.run("pkill -f '/code-insiders|/usr/share/code/code' || true", shell=True)
    for pkg, build, _ in BUILDS:
        subprocess.run(f'curl -L "https://code.visualstudio.com/sha/download?build={build}&os=linux-deb-x64" -o /tmp/{pkg}.deb && {sudo(f"apt install /tmp/{pkg}.deb -y --allow-downgrades")} && rm /tmp/{pkg}.deb', shell=True, check=True); print(f"Installed {pkg}")
    setup_aliases(); apply_settings()

def setup_aliases():
    aliases = {f"alias {a}='{p}'" for p, _, a in BUILDS}
    content = open(BASHRC).read() if os.path.exists(BASHRC) else ""
    new = [a for a in aliases if a not in content]
    if new: open(BASHRC, "a").write("\n" + "\n".join(new) + "\n"); print(f"Added aliases: {', '.join(a.split('=')[0].split()[1] for a in new)}")

def apply_settings():
    for p in [os.path.expanduser(x) for x in SETTINGS]:
        s = json.load(open(p)) if os.path.exists(p) else {}
        s["git.decorations.enabled"] = False
        os.makedirs(os.path.dirname(p), exist_ok=True); json.dump(s, open(p, "w"), indent=2); print(f"Settings: {p}")

if __name__ == "__main__":
    {"install": install, "settings": apply_settings, "aliases": setup_aliases}.get(sys.argv[1] if len(sys.argv) > 1 else "install", install)()
