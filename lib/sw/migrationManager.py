#!/usr/bin/env python3
"""Migration Manager - Save/restore system setup across devices."""
import subprocess, sys, json, os, shutil
from pathlib import Path

SCRIPT_DIR, MIGRATION_DIR = Path(__file__).parent, Path(__file__).parent / "migration"
_U = os.environ.get('SUDO_USER'); HOME = Path(f"/home/{_U}") if _U else Path.home(); PROJECTS_DIR = HOME / "projects"
AUTO_YES = "-y" in sys.argv or not sys.stdin.isatty(); SU = f"sudo -u {_U} " if _U else ""
def run(cmd): return subprocess.run(cmd, shell=True, capture_output=True, text=True)
def confirm(msg): return True if AUTO_YES else input(f"{msg} [y/N]: ").lower() == 'y'
def safe(fn, default=None):
    try: return fn()
    except Exception as e: print(f"  Error: {e}"); return default or []

def get_gnome():
    exts = run("gnome-extensions list --enabled").stdout.strip().split('\n') if run("which gnome-extensions").returncode == 0 else []
    dconf = run("dconf dump /org/gnome/shell/").stdout
    favs = run("gsettings get org.gnome.shell favorite-apps").stdout.strip()
    return {"extensions": [e for e in exts if e], "dconf": dconf, "favorites": favs}

def get_wallpaper():
    wp = run("gsettings get org.gnome.desktop.background picture-uri").stdout.strip().strip("'").replace("file://", "")
    if wp and Path(wp).exists(): shutil.copy(wp, SCRIPT_DIR / Path(wp).name); return Path(wp).name
    return None
def get_apt_repos():
    repos, src, keys = [], Path("/etc/apt/sources.list.d"), Path("/etc/apt/keyrings")
    if not src.exists(): return repos
    for f in src.iterdir():
        if f.suffix in ['.list', '.sources'] and not f.name.endswith('.save') and not f.name.startswith('ubuntu'):
            try:
                keyring = next(({"name": k.name, "data": k.read_bytes().hex()} for k in keys.glob(f"{f.stem.split('-')[0]}*.gpg")), None) if keys.exists() else None
                repos.append({"name": f.name, "content": f.read_text(), "keyring": keyring})
            except: pass
    return repos

def get_apt(): r = run("apt-mark showmanual"); return sorted(r.stdout.strip().split('\n')) if r.returncode == 0 else []
def get_snap(): r = run("snap list"); return [l.split()[0] for l in r.stdout.strip().split('\n')[1:] if l] if r.returncode == 0 else []
def get_flatpak(): fps = [l.strip() for l in run("flatpak list --app --columns=application").stdout.split('\n') if l.strip()]; return fps + (["app.devsuite.Ptyxis"] if run("which ptyxis").returncode == 0 and "app.devsuite.Ptyxis" not in fps else [])  # ptyxis: apt=Ubuntu default, flatpak=newer; both coexist

def get_repos():
    repos = []
    if not PROJECTS_DIR.exists(): return repos
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir() and (d / ".git").exists():
            r = run(f"git -C '{d}' remote get-url origin")
            if r.returncode == 0 and r.stdout.strip(): repos.append({"name": d.name, "url": r.stdout.strip()})
    return repos

def get_info():
    print("=== Gathering System Info ===\n")
    try: MIGRATION_DIR.mkdir(exist_ok=True)
    except Exception as e: print(f"Error: {e}"); return False

    for name, fn, file in [
        ("Apt repos", get_apt_repos, "apt_repos.json"),
        ("Apt packages", get_apt, "apt_packages.txt"),
        ("Snap packages", get_snap, "snap_packages.txt"),
        ("Flatpak packages", get_flatpak, "flatpak_packages.txt"),
        ("Git repos", get_repos, "git_repos.json"),
        ("GNOME settings", get_gnome, "gnome.json"),
        ("Wallpaper", get_wallpaper, "wallpaper.txt"),
    ]:
        try:
            data = safe(fn)
            (MIGRATION_DIR / file).write_text(json.dumps(data, indent=2) if file.endswith('.json') else (data if isinstance(data, str) else '\n'.join(data or [])))
            print(f"{name}: {len(data) if data else 0}")
        except Exception as e: print(f"Error saving {name}: {e}")

    try:
        installers = [f.stem for f in SCRIPT_DIR.glob("*.py") if f.stem not in ["migrationManager", "__init__"]]
        (MIGRATION_DIR / "installers.txt").write_text('\n'.join(installers))
        print(f"Installers: {len(installers)}")
    except: pass
    print(f"\nSaved to: {MIGRATION_DIR}/")

def restore():
    if not MIGRATION_DIR.exists(): print("No migration data. Run 'get_info' first."); return
    print("=== System Restore ===\n")

    # GitHub auth
    print("1. GitHub Auth")
    try:
        if run(f"{SU}gh auth status").returncode != 0: print("Sign in:"); subprocess.run(f"{SU}gh auth login", shell=True)
        else: print("Already signed in.")
    except Exception as e: print(f"Error: {e}")

    # Clone repos
    print("\n2. Clone Repos")
    try:
        f = MIGRATION_DIR / "git_repos.json"
        if f.exists():
            PROJECTS_DIR.mkdir(exist_ok=True)
            for repo in json.loads(f.read_text()):
                dest = PROJECTS_DIR / repo["name"]; slug = repo['url'].replace('https://github.com/','').replace('git@github.com:','').replace('.git','')
                if dest.exists(): print(f"  Skip: {repo['name']}")
                else: print(f"  Clone: {repo['name']}"); subprocess.run(f"{SU}gh repo clone {slug} {dest}", shell=True)
    except Exception as e: print(f"Error: {e}")

    # Apt repos
    print("\n3. Apt Repos")
    try:
        f = MIGRATION_DIR / "apt_repos.json"
        if f.exists():
            repos = json.loads(f.read_text())
            if repos and confirm(f"Restore {len(repos)} repos?"):
                for r in repos:
                    if r.get('keyring'): subprocess.run(f"sudo mkdir -p /etc/apt/keyrings && sudo tee /etc/apt/keyrings/{r['keyring']['name']}", shell=True, input=bytes.fromhex(r['keyring']['data']), stdout=subprocess.DEVNULL)
                    print(f"  Adding: {r['name']}"); subprocess.run(f"sudo tee /etc/apt/sources.list.d/{r['name']}", shell=True, input=r['content'], text=True, stdout=subprocess.DEVNULL)
                subprocess.run("sudo apt update", shell=True)
    except Exception as e: print(f"Error: {e}")

    # Apt packages
    print("\n4. Apt Packages")
    try:
        f = MIGRATION_DIR / "apt_packages.txt"
        if f.exists():
            pkgs = [p for p in f.read_text().strip().split('\n') if not p.startswith('lib') and p not in ['base-files', 'bash', 'coreutils']]
            if pkgs and confirm(f"Install {len(pkgs)} packages?"):
                for p in pkgs: subprocess.run(["sudo", "apt", "install", "-y", p], stderr=subprocess.DEVNULL)
    except Exception as e: print(f"Error: {e}")

    # Snaps
    print("\n5. Snaps")
    try:
        f = MIGRATION_DIR / "snap_packages.txt"
        if f.exists():
            snaps = [s for s in f.read_text().strip().split('\n') if s and s not in ['core', 'core20', 'core22', 'core24', 'snapd', 'bare']]
            if snaps and confirm(f"Install {len(snaps)} snaps?"):
                for s in snaps: print(f"  Installing: {s}"); subprocess.run(["sudo", "snap", "install", s])
    except Exception as e: print(f"Error: {e}")

    # Flatpaks
    print("\n6. Flatpaks")
    try:
        f = MIGRATION_DIR / "flatpak_packages.txt"
        if f.exists():
            fps = [p for p in f.read_text().strip().split('\n') if p]
            if fps and confirm(f"Install {len(fps)} flatpaks?"):
                subprocess.run(["sudo", "apt", "install", "-y", "flatpak"], stderr=subprocess.DEVNULL); subprocess.run(["flatpak", "remote-add", "--if-not-exists", "flathub", "https://flathub.org/repo/flathub.flatpakrepo"])
                for p in fps: print(f"  Installing: {p}"); subprocess.run(["flatpak", "install", "-y", "flathub", p])
    except Exception as e: print(f"Error: {e}")

    # GNOME settings + Wallpaper
    print("\n7. GNOME Settings & Wallpaper")
    try:
        if (f := MIGRATION_DIR / "gnome.json").exists() and (g := json.loads(f.read_text())):
            if g.get("extensions") and confirm(f"Install {len(g['extensions'])} extensions?"):
                for e in g["extensions"]:
                    if "dash-to-panel" in e: subprocess.run([sys.executable, str(SCRIPT_DIR / "dash_to_panel_manager.py"), "install"]); print("  *** LOG OUT/IN REQUIRED for dash-to-panel ***")
                    else: subprocess.run(f"gnome-extensions install {e} 2>/dev/null", shell=True); print(f"  {e}")
            if g.get("dconf") and confirm("Apply dconf?"): subprocess.run("dconf load /org/gnome/shell/", shell=True, input=g["dconf"], text=True); print("  Applied")
        wp = next((f for f in SCRIPT_DIR.glob("*.png") if f.name == "black_focus.png"), None)
        if wp and confirm(f"Set wallpaper {wp.name}?"): dest = HOME / ".local/share/backgrounds" / wp.name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy(wp, dest); [subprocess.run(f"gsettings set org.gnome.desktop.background {k} 'file://{dest}'", shell=True) for k in ["picture-uri", "picture-uri-dark"]]; print(f"  Set: {dest}")
    except Exception as e: print(f"Error: {e}")

    # Installers
    print("\n8. Custom Installers")
    try:
        f = MIGRATION_DIR / "installers.txt"
        if f.exists(): print(f"Available: {', '.join(f.read_text().strip().split())}\nRun: python3 <installer>.py")
    except: pass
    print("\n=== Done ===")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if not cmd and sys.stdin.isatty():
        print("Migration Manager\n\nAI Agent? Choose: [s]ave current system info, [a]pply saved data, [q]uit")
        c = input("> ").lower()
        cmd = "get_info" if c == "s" else "restore" if c == "a" else ""
    if cmd == "get_info": get_info()
    elif cmd == "restore": restore()
    else: print("Commands: get_info (save), restore (apply)")
