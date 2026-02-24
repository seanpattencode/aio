import subprocess, sys, argparse, shutil, json, urllib.request, urllib.error, getpass, os, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import apt_config

failed_updates = []

# Android SDK Configuration
JAVA_TARGET_MAJOR = 25
GRADLE_TARGET_VERSION = "9.2.1"
ADB_TARGET_VERSION = "36.0.2"
AGP_TARGET_VERSION = "8.13.2"
ANDROID_DEMO_APP_PATH = Path("AndroidDemoApp")

# Detect Termux environment
IS_TERMUX = os.environ.get("TERMUX_VERSION") is not None or os.path.exists("/data/data/com.termux/files/usr")
# Detect Arch Linux
IS_ARCH = os.path.exists("/etc/arch-release")

try: import keyring
except ImportError: keyring = None

def store_sudo_password():
    """Store sudo password in system keyring."""
    if IS_TERMUX:
        print("Termux detected - sudo not used, password storage not needed.")
        return True
    if not keyring:
        if IS_ARCH:
            print("Installing python-keyring...")
            subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "python-keyring", "python-keyrings-alt"])
            print("Restart script to use keyring.")
            return False
        else:
            print("keyring not installed. Run: pip install keyring keyrings.alt")
            return False
    print("⚠️  Password stored in keyring - accessible by processes running as your user.")
    pw = getpass.getpass("Sudo password: ")
    # Verify password works
    if subprocess.run(["sudo", "-S", "-v"], input=pw, text=True, capture_output=True).returncode != 0:
        print("Invalid password.")
        return False
    keyring.set_password("softwaremanager", "sudo", pw)
    print("Password stored.")
    return True

def init_sudo():
    """Cache sudo credentials from stored password."""
    if IS_TERMUX:
        return True  # No sudo needed in Termux
    pw = keyring and keyring.get_password("softwaremanager", "sudo")
    return pw and subprocess.run(["sudo", "-S", "-v"], input=pw, text=True, capture_output=True).returncode == 0


def run_command(command, description):
    """Run a command and return True on success, False on failure (continues on error)."""
    print(f"--- {description} ---")
    try:
        # Inject stored sudo password if command uses sudo
        inp = None
        if "sudo " in command and not IS_TERMUX:
            pw = keyring and keyring.get_password("softwaremanager", "sudo")
            if pw:
                command = command.replace("sudo ", "sudo -S ", 1)
                inp = pw
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True, executable="/bin/bash", input=inp)
        print(result.stdout)
        if result.stderr and "[sudo]" not in result.stderr:
            print(f"Stderr during {description}:\n{result.stderr}", file=sys.stderr)
        print(f"--- {description} completed successfully ---")
        return True
    except subprocess.CalledProcessError as e:
        if "Authentication failed" in (e.stderr or "") or "password" in (e.stderr or "").lower():
            print(f"Sudo authentication failed. Fix: run 'sudo -v' first, or use --store-password", file=sys.stderr)
        else:
            print(f"Error during {description}: {e.stderr or e.stdout or f'exit {e.returncode}'}", file=sys.stderr)
        failed_updates.append(description)
        return False
    except FileNotFoundError:
        print(f"Error: Command not found. Make sure '{command.split()[0]}' is installed and in your PATH.", file=sys.stderr)
        failed_updates.append(description)
        return False
    except Exception as e:
        print(f"An unexpected error occurred during {description}: {e}", file=sys.stderr)
        failed_updates.append(description)
        return False


def run_installer(script_name, description, args=[], timeout=600):
    """Run an installer script and return True on success, False on failure."""
    print(f"\n{'='*50}")
    print(f"--- {description} ---")
    print(f"{'='*50}")

    script_path = Path(__file__).parent / script_name

    if not script_path.exists():
        print(f"Error: {script_path} not found", file=sys.stderr)
        failed_updates.append(description)
        return False

    try:
        env = None
        if not IS_TERMUX:
            pw = keyring and keyring.get_password("softwaremanager", "sudo")
            if pw:
                env = {**os.environ, "SUDO_PW": pw}
        result = subprocess.run(
            [sys.executable, str(script_path)] + args, check=True, timeout=timeout, env=env
        )
        print(f"--- {description} completed successfully ---")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error during {description}: Return code {e.returncode}", file=sys.stderr)
        failed_updates.append(description)
        return False
    except Exception as e:
        print(f"An unexpected error occurred during {description}: {e}", file=sys.stderr)
        failed_updates.append(description)
        return False


def ensure_ollama_running(max_retries=10, initial_wait=2):
    """Ensure ollama service is running with retry logic."""
    import time

    # Check if ollama is installed
    if not shutil.which("ollama"):
        return False

    def check_ollama_ready():
        """Check if ollama responds and returns models."""
        result = subprocess.run(
            "ollama list",
            shell=True,
            capture_output=True,
            text=True
        )
        return result.returncode == 0

    # Try immediately first
    if check_ollama_ready():
        return True

    # Check if systemd is managing ollama (skip on Termux - no systemd)
    systemd_managed = False
    if not IS_TERMUX:
        systemd_managed = subprocess.run(
            "systemctl is-active ollama",
            shell=True,
            capture_output=True,
            text=True
        ).returncode == 0 or subprocess.run(
            "systemctl is-enabled ollama",
            shell=True,
            capture_output=True,
            text=True
        ).returncode == 0

    if systemd_managed:
        # Restart via systemd and wait for it to be ready
        print("Ollama not responding, restarting systemd service...")
        subprocess.run("sudo systemctl restart ollama", shell=True, capture_output=True)
    else:
        # Try to start ollama serve in background (no systemd)
        print("Ollama not responding, attempting to start service...")
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    # Retry with exponential backoff
    wait_time = initial_wait
    for attempt in range(max_retries):
        print(f"Waiting for Ollama service to be ready (attempt {attempt + 1}/{max_retries})...")
        time.sleep(wait_time)

        if check_ollama_ready():
            print("Ollama service is ready.")
            return True

        # Exponential backoff, max 10 seconds between retries
        wait_time = min(wait_time * 1.5, 10)

    print("Ollama service failed to respond after retries.")
    return False


def get_remote_ollama_digest(model_name):
    """Query Ollama registry to get the remote model digest.

    Returns the first 12 chars of the manifest's sha256 hash (matches ollama list ID format),
    or None if the check fails.
    """
    import hashlib

    # Parse model name and tag
    if ':' in model_name:
        name, tag = model_name.split(':', 1)
    else:
        name, tag = model_name, 'latest'

    # Handle namespaced vs library models
    if '/' in name:
        registry_path = name
    else:
        registry_path = f"library/{name}"

    url = f"https://registry.ollama.ai/v2/{registry_path}/manifests/{tag}"

    try:
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/vnd.docker.distribution.manifest.v2+json')
        with urllib.request.urlopen(req, timeout=15) as response:
            # The ollama list ID is the sha256 of the manifest content itself
            manifest_content = response.read()
            manifest_hash = hashlib.sha256(manifest_content).hexdigest()
            return manifest_hash[:12]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  Warning: Model {model_name} not found in registry")
        else:
            print(f"  Warning: HTTP {e.code} checking {model_name}")
        return None
    except Exception as e:
        print(f"  Warning: Could not check remote version for {model_name}: {e}")
        return None


def update_ollama_models():
    """Update all installed Ollama models (only downloads if update available)."""
    print("--- Checking Ollama models for updates ---")

    # Check if ollama is installed
    if not shutil.which("ollama"):
        print("Error: ollama not found. Install it first.", file=sys.stderr)
        failed_updates.append("Updating Ollama models")
        return False

    # Ensure service is running
    if not ensure_ollama_running():
        print("Error: Could not start ollama service.", file=sys.stderr)
        failed_updates.append("Updating Ollama models")
        return False

    try:
        # Get list of installed models
        result = subprocess.run(
            "ollama list",
            shell=True,
            check=True,
            text=True,
            capture_output=True
        )

        # Parse model names and IDs (skip header line)
        # Format: NAME  ID  SIZE  MODIFIED
        lines = result.stdout.strip().split('\n')
        if len(lines) <= 1:
            print("No Ollama models installed.")
            return True

        models = []
        for line in lines[1:]:
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    models.append((parts[0], parts[1]))  # (name, local_id)

        if not models:
            print("No Ollama models found.")
            return True

        print(f"Found {len(models)} model(s): {', '.join(m[0] for m in models)}")
        print("Checking for updates...")

        # Check which models need updates
        models_to_update = []
        models_up_to_date = []
        models_check_failed = []

        for model_name, local_id in models:
            remote_id = get_remote_ollama_digest(model_name)
            if remote_id is None:
                # Couldn't check - will pull to be safe
                models_check_failed.append(model_name)
            elif remote_id != local_id:
                models_to_update.append((model_name, local_id, remote_id))
            else:
                models_up_to_date.append(model_name)

        # Report status
        if models_up_to_date:
            print(f"\nUp to date ({len(models_up_to_date)}): {', '.join(models_up_to_date)}")

        if models_check_failed:
            print(f"\nCould not check ({len(models_check_failed)}): {', '.join(models_check_failed)}")
            print("  These will be pulled to ensure they're current.")

        if models_to_update:
            print(f"\nUpdates available ({len(models_to_update)}):")
            for name, old_id, new_id in models_to_update:
                print(f"  {name}: {old_id} -> {new_id}")
        elif not models_check_failed:
            print("\nAll models are up to date!")
            return True

        # Pull models that need updates (or couldn't be checked)
        all_to_pull = [(m[0], "update") for m in models_to_update] + [(m, "verify") for m in models_check_failed]

        if not all_to_pull:
            return True

        model_failures = []
        for model, reason in all_to_pull:
            print(f"\nPulling {model} ({reason})...")
            try:
                subprocess.run(
                    f"ollama pull {model}",
                    shell=True,
                    check=True
                )
                print(f"Model {model} updated successfully")
            except subprocess.CalledProcessError as e:
                print(f"Failed to update model {model}: {e}", file=sys.stderr)
                model_failures.append(model)
            print("--")

        if model_failures:
            print(f"Failed to update {len(model_failures)} model(s): {', '.join(model_failures)}", file=sys.stderr)
            failed_updates.append(f"Ollama models ({', '.join(model_failures)})")
            return False

        print("--- Ollama model updates completed successfully ---")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error listing Ollama models: {e}", file=sys.stderr)
        if e.stderr:
            print(f"Stderr: {e.stderr}", file=sys.stderr)
        failed_updates.append("Updating Ollama models")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        failed_updates.append("Updating Ollama models")
        return False

def update_vscode():
    """Install/update VS Code stable + Insiders with aliases (code=insiders, code-stable=stable)."""
    if IS_TERMUX:
        print("VS Code not available on Termux, skipping.")
        return True
    return run_installer("vscode_manager.py", "Installing/updating VS Code", ["install"])


def get_java_version():
    """Get the current major Java version."""
    result = subprocess.run("java -version", shell=True, capture_output=True, text=True)
    output = result.stderr or result.stdout  # java -version outputs to stderr
    match = re.search(r'version "(\d+)', output)
    return int(match.group(1)) if match else 0


def update_java():
    """Update Java to the target version."""
    print("--- Checking Java version ---")
    current = get_java_version()
    if current >= JAVA_TARGET_MAJOR:
        print(f"Java is up to date ({current})")
        return True

    print(f"Updating Java from {current} to {JAVA_TARGET_MAJOR}...")

    # Update package lists
    if not run_command("sudo apt-get update", "Updating package lists"):
        failed_updates.append("Java update (apt update failed)")
        return False

    # Install target Java version
    if not run_command(f"sudo apt-get install -y openjdk-{JAVA_TARGET_MAJOR}-jdk", f"Installing openjdk-{JAVA_TARGET_MAJOR}-jdk"):
        failed_updates.append(f"Java update (install openjdk-{JAVA_TARGET_MAJOR}-jdk failed)")
        return False

    # Verify installation
    pkg_result = subprocess.run(f"dpkg -s openjdk-{JAVA_TARGET_MAJOR}-jdk", shell=True, capture_output=True, text=True)
    if pkg_result.returncode != 0:
        print(f"Package openjdk-{JAVA_TARGET_MAJOR}-jdk verification failed", file=sys.stderr)
        failed_updates.append("Java update (verification failed)")
        return False

    # Check if we need to switch alternatives
    new_ver = get_java_version()
    if new_ver >= JAVA_TARGET_MAJOR:
        print(f"Java updated to {new_ver}")
        return True

    print(f"Installed, but active version is {new_ver}. Switching system default...")
    jvm_dir = Path("/usr/lib/jvm")
    target_path = None

    if jvm_dir.exists():
        for path in jvm_dir.glob(f"java-{JAVA_TARGET_MAJOR}-*"):
            java_bin = path / "bin" / "java"
            if java_bin.exists():
                target_path = str(java_bin)
                break

    if target_path:
        print(f"Found new Java at: {target_path}")
        run_command(f"sudo update-alternatives --set java {target_path}", "Switching Java alternative")
        javac_path = target_path.replace("bin/java", "bin/javac")
        if os.path.exists(javac_path):
            run_command(f"sudo update-alternatives --set javac {javac_path}", "Switching javac alternative")

        final_ver = get_java_version()
        if final_ver >= JAVA_TARGET_MAJOR:
            print(f"Successfully switched to Java {final_ver}")
            return True
        print(f"Failed to switch. Active version is still {final_ver}", file=sys.stderr)
        failed_updates.append("Java update (alternative switch failed)")
        return False
    else:
        print(f"Could not locate java-{JAVA_TARGET_MAJOR}-* in /usr/lib/jvm/", file=sys.stderr)
        failed_updates.append("Java update (binary not found)")
        return False


def get_gradle_version():
    """Get the current Gradle version."""
    sdkman_path = os.path.expanduser("~/.sdkman/candidates/gradle/current/bin/gradle")
    cmd = f"{sdkman_path} -v" if os.path.exists(sdkman_path) else "gradle -v"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    match = re.search(r'Gradle (\d+\.\d+(\.\d+)?)', result.stdout)
    return match.group(1) if match else "0.0.0"


def update_gradle():
    """Update Gradle to the target version via SDKMAN."""
    print("--- Checking Gradle version ---")
    current = get_gradle_version()
    if current == GRADLE_TARGET_VERSION:
        print(f"Gradle is up to date ({current})")
        return True

    print(f"Updating Gradle from {current} to {GRADLE_TARGET_VERSION}...")
    sdkman_init = os.path.expanduser("~/.sdkman/bin/sdkman-init.sh")
    if not os.path.exists(sdkman_init):
        print("SDKMAN not found. Install SDKMAN first.", file=sys.stderr)
        failed_updates.append("Gradle update (SDKMAN not found)")
        return False

    cmd = f'source "{sdkman_init}" && sdk install gradle {GRADLE_TARGET_VERSION}'
    if not run_command(cmd, f"Installing Gradle {GRADLE_TARGET_VERSION} via SDKMAN"):
        failed_updates.append("Gradle update")
        return False
    print(f"Gradle updated to {GRADLE_TARGET_VERSION}")
    return True


def get_adb_version():
    """Get the current ADB version."""
    adb_path = os.path.expanduser("~/Android/Sdk/platform-tools/adb")
    if not os.path.exists(adb_path):
        return "0.0.0"
    result = subprocess.run(f"{adb_path} --version", shell=True, capture_output=True, text=True)
    match = re.search(r'Version (\d+\.\d+\.\d+)', result.stdout)
    return match.group(1) if match else "0.0.0"


def update_adb():
    """Update ADB/platform-tools via Android SDK manager."""
    print("--- Checking ADB version ---")
    current = get_adb_version()
    if current == ADB_TARGET_VERSION:
        print(f"ADB is up to date ({current})")
        return True

    print(f"Updating ADB from {current} to {ADB_TARGET_VERSION}...")
    sdkmanager = os.path.expanduser("~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager")
    if not os.path.exists(sdkmanager):
        print("sdkmanager not found. Install Android SDK cmdline-tools first.", file=sys.stderr)
        failed_updates.append("ADB update (sdkmanager not found)")
        return False

    cmd = f"yes | {sdkmanager} --update"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ADB update failed: {result.stderr}", file=sys.stderr)
        failed_updates.append("ADB update")
        return False
    print("ADB updated")
    return True


def update_agp():
    """Update Android Gradle Plugin version in build.gradle if present."""
    build_gradle = ANDROID_DEMO_APP_PATH / "build.gradle"
    if not build_gradle.exists():
        return True  # No Android project, skip silently

    content = build_gradle.read_text()
    match = re.search(r"id 'com.android.application' version '([\d\.]+)'", content)
    if not match:
        return True

    current = match.group(1)
    if current == AGP_TARGET_VERSION:
        print(f"AGP is up to date ({current})")
        return True

    print(f"Updating AGP from {current} to {AGP_TARGET_VERSION}...")
    build_gradle.write_text(re.sub(
        r"id 'com.android.application' version '[\d\.]+'",
        f"id 'com.android.application' version '{AGP_TARGET_VERSION}'", content))
    print(f"AGP updated to {AGP_TARGET_VERSION}")
    return True


def get_calibre_versions():
    inst = (m := re.search(r'calibre (\d+\.\d+\.\d+)', subprocess.run("calibre --version", shell=True, capture_output=True, text=True).stdout)) and m.group(1) if shutil.which("calibre") else None
    try: return inst, json.loads(urllib.request.urlopen(urllib.request.Request("https://api.github.com/repos/kovidgoyal/calibre/releases/latest"), timeout=10).read()).get("tag_name", "").lstrip("v")
    except: return inst, None

def update_calibre():
    inst, latest = get_calibre_versions()
    if inst and latest and inst == latest: return print(f"Calibre up to date ({inst})") or True
    print(f"Updating Calibre: {inst or 'N/A'} -> {latest or 'latest'}..."); return run_command("sudo -v && wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh | sudo sh /dev/stdin", "Installing/updating Calibre")

def get_ollama_versions():
    """Get installed and latest ollama versions."""
    installed = None
    if shutil.which("ollama"):
        result = subprocess.run("ollama --version", shell=True, capture_output=True, text=True)
        match = re.search(r'(\d+\.\d+\.\d+)', result.stdout)
        if match:
            installed = match.group(1)
    try:
        req = urllib.request.Request("https://api.github.com/repos/ollama/ollama/releases/latest")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            latest = data.get("tag_name", "").lstrip("v")
            return installed, latest
    except:
        return installed, None


def update_ollama():
    """Install/update Ollama only if newer version available."""
    installed, latest = get_ollama_versions()
    if installed and latest and installed == latest:
        print(f"Ollama is up to date ({installed})")
        return True
    print(f"Updating Ollama: {installed or 'not installed'} -> {latest or 'latest'}...")
    return run_command("curl -fsSL https://ollama.com/install.sh | sh", "Installing/updating Ollama")


def find_conda_installation():
    """Find conda/mamba installations by checking common paths."""
    home = Path.home()
    # Check paths in order of preference (miniforge/mambaforge preferred for mamba)
    candidates = [
        home / "miniforge3",
        home / "mambaforge",
        home / "miniconda3",
        home / "anaconda3",
        Path("/opt/conda"),
        Path("/opt/miniconda3"),
        Path("/opt/anaconda3"),
    ]

    installations = []
    for path in candidates:
        if path.exists() and (path / "bin" / "conda").exists():
            has_mamba = (path / "bin" / "mamba").exists() or (path / "bin" / "micromamba").exists()
            installations.append((path, has_mamba))

    return installations


def get_conda_shell_init(conda_prefix):
    """Get the shell command to initialize conda/mamba."""
    init_script = conda_prefix / "etc" / "profile.d" / "conda.sh"
    mamba_script = conda_prefix / "etc" / "profile.d" / "mamba.sh"

    # Set MAMBA_ROOT_PREFIX to avoid warnings in mamba 2.0+
    init_cmd = f'export MAMBA_ROOT_PREFIX="{conda_prefix}"'
    if init_script.exists():
        init_cmd += f' && source "{init_script}"'
    if mamba_script.exists():
        init_cmd += f' && source "{mamba_script}"'

    return init_cmd


def update_conda_mamba():
    """Update conda/mamba/micromamba packages. Uses mamba_manager for install if needed."""
    print("--- Detecting conda/mamba/micromamba installation ---")

    # Check for micromamba first (preferred), then mamba/conda
    micromamba_bin = Path.home() / ".local/bin/micromamba"
    micromamba_dir = Path.home() / "micromamba"
    mamba_dir = Path.home() / "miniforge3"

    has_micromamba = micromamba_bin.exists() or shutil.which("micromamba")
    has_mamba = shutil.which("mamba") or (mamba_dir / "bin/mamba").exists()
    has_conda = shutil.which("conda") or (mamba_dir / "bin/conda").exists()

    if not has_micromamba and not has_mamba and not has_conda:
        # Check old-style installations
        installations = find_conda_installation()
        if not installations:
            if input("No conda/mamba found. Install micromamba? [y/N]: ").lower() != 'y':
                return True
            # Install micromamba (default) - use --mamba flag for mamba instead
            return run_installer("mamba_manager.py", "Installing micromamba", ["install"])
        # Use found installation
        conda_prefix, has_mamba = installations[0]
    else:
        conda_prefix = micromamba_dir if has_micromamba else mamba_dir

    # Micromamba path
    if has_micromamba:
        mm = str(micromamba_bin) if micromamba_bin.exists() else "micromamba"
        # Micromamba base env is at root prefix, not envs/base
        base_env = micromamba_dir
        print(f"Using micromamba at {mm}")

        # Create base env if missing
        if not base_env.exists():
            print("Base env not found, creating...")
            if not run_command(
                f"{mm} create -y -p {base_env} -c conda-forge python",
                "Creating micromamba base env"
            ):
                failed_updates.append("Creating micromamba base")
                return False

        success = True

        # Update base env - no-pin allows python major.minor upgrade (3.14→3.15)
        # Packages may need reinstall after python upgrade
        if not run_command(
            f"{mm} update -p {base_env} --all -y --no-pin",
            "Updating micromamba base packages (latest stable python)"
        ):
            success = False

        # Clean cache
        run_command(f"{mm} clean --all -y", "Cleaning micromamba cache")

        # Persist to .bashrc so python/python3 uses micromamba
        run_installer("mamba_manager.py", "Persisting micromamba to shell", ["persist"])

        if not success:
            failed_updates.append("Updating micromamba")
        return success

    # Mamba/conda path
    shell_init = get_conda_shell_init(conda_prefix) if conda_prefix else ""
    cmd_prefix = f"{shell_init} && " if shell_init else ""
    pkg_manager = "mamba" if has_mamba else "conda"

    print(f"Using {pkg_manager} at {conda_prefix or 'PATH'}")

    def run_conda_cmd(cmd, description):
        return run_command(f'{cmd_prefix}{cmd}', description)

    success = True

    # Update package manager
    if has_mamba:
        if not run_conda_cmd(f"{pkg_manager} update -n base mamba conda -y", f"Updating {pkg_manager}"):
            success = False
    else:
        if not run_conda_cmd("conda update -n base conda -y", "Updating conda"):
            success = False

    # Update all base packages
    if not run_conda_cmd(f"{pkg_manager} update -n base --all -y", f"Updating base packages"):
        success = False

    # Clean cache
    run_conda_cmd(f"{pkg_manager} clean --all -y", f"Cleaning cache")

    if not success:
        failed_updates.append(f"Updating {pkg_manager}")
    return success


# Termux-specific update tasks (no sudo, different package managers)
TERMUX_UPDATE_TASKS = {
    "npm": ("Updating npm + claude", lambda: run_command("npm update -g npm @anthropic-ai/claude-code 2>/dev/null; npm outdated -g || true", "Updating npm and claude-code")),
    "pkg": ("Updating Termux packages", lambda: run_command("pkg update -y && pkg upgrade -y", "Updating Termux packages")),
    "pip": ("Updating pip packages", lambda: run_command("pip install -U pip 2>/dev/null; pip list -o --format=json 2>/dev/null | python -c \"import sys,json;[print(p['name']) for p in json.load(sys.stdin)]\" | xargs -r pip install -U 2>/dev/null || true", "Updating pip")),
}

TERMUX_DEFAULT_ORDER = ["npm", "pkg", "pip"]

def update_apt():
    """Update apt packages using per-machine config."""
    import time
    cfg = apt_config.load()
    mode = cfg.get("mode", "default")
    print(f"[apt config] {apt_config.get_machine_name()}: {mode}")

    if mode == "fast-stable-kernel":
        is_setup, missing = apt_config.check_fast_stable_kernel_setup()
        if not is_setup:
            if init_sudo():
                print("fast-stable-kernel: auto-configuring...")
                for cmd in missing: subprocess.run(cmd, shell=True)
            else:
                print("fast-stable-kernel not configured. Run these:")
                for cmd in missing: print(f"  {cmd}")
                print("Continuing in 10s..."); time.sleep(10)

    if not init_sudo() and subprocess.run(["sudo", "-v"]).returncode != 0:
        failed_updates.append("apt (sudo auth)")
        return False
    # Install browser insider channels if available but missing
    BROWSER_PKGS = ["microsoft-edge-beta", "microsoft-edge-dev", "google-chrome-beta", "google-chrome-unstable"]
    missing_pkgs = [p for p in BROWSER_PKGS if subprocess.run(["dpkg", "-s", p], capture_output=True).returncode != 0
                    and subprocess.run(["apt-cache", "show", p], capture_output=True).returncode == 0]
    install_cmd = f"sudo apt-get install -y {' '.join(missing_pkgs)}; " if missing_pkgs else ""
    if missing_pkgs:
        print(f"Installing missing browser channels: {', '.join(missing_pkgs)}")
    return run_command(f"sudo dpkg --configure -a; sudo apt --fix-broken install -y; sudo apt-get update || true; {install_cmd}{apt_config.get_cmd(mode)}", "Upgrading apt packages")

def update_pacman():
    """Update Arch Linux packages via pacman."""
    # Reflector: pick freshest mirrors (sorted by last sync time, not speed)
    # This gets packages ~1hr after repo publish vs 12hr+ with stale mirrors
    if shutil.which("reflector"):
        run_command("sudo reflector --latest 5 --sort age --save /etc/pacman.d/mirrorlist", "Refreshing mirrors (freshest)")
    return run_command("sudo pacman -Syu --noconfirm", "Upgrading pacman packages")

# Standard Linux update tasks (with sudo)
LINUX_UPDATE_TASKS = {
    "apt": ("Updating apt packages", update_apt),
    "node": ("Installing/updating Node.js", lambda: run_command(
        "sudo npm install -g n && sudo n latest && sudo npm install -g npm",
        "Installing latest Node.js via n"
    )),
    "npm": ("Updating npm global packages", lambda: run_command(
        "npm outdated -g; sudo npm update -g",
        "Updating npm global packages"
    )),
    "conda": ("Updating conda/mamba/micromamba", update_conda_mamba),
    "flatpak": ("Updating flatpak", lambda: run_command(
        "flatpak update -y && flatpak uninstall --unused -y",
        "Updating flatpak"
    )),
    "snap": ("Updating snap", lambda: run_command(
        "sudo snap refresh",
        "Updating snap packages"
    )),
    "calibre": ("Updating Calibre", update_calibre),
    "tmux": ("Building Tmux from source", lambda: run_installer("tmux_installer.py", "Building and installing Tmux", ["install"], 1800)),
    # Ptyxis: default terminal on Fedora 42+ (GNOME 47+). VTE/GTK4. What Torvalds uses
    # All three show ~0ms for fast commands. Latency difference is in rendering pipeline, not shell timing:
    #   ptyxis: VTE/Cairo CPU render, no vsync gate. Best GNOME integration (tabs, desktop file, dbus)
    #   alacritty: OpenGL GPU render + vsync. Best throughput for large output (cat 10MB)
    #   foot: pixman CPU render, direct Wayland, no toolkit. Lowest theoretical latency, most spartan
    "ptyxis": ("Building Ptyxis from source", lambda: run_installer("ptyxis_installer.py", "Building and installing Ptyxis", ["install"], 1800)),
    "alacritty": ("Building Alacritty from source", lambda: run_installer("alacritty_installer.py", "Building and installing Alacritty", ["install"], 1800)),
    "foot": ("Building foot from source", lambda: run_installer("foot_installer.py", "Building and installing foot", ["install"], 1800)),
    "clang": ("Building Clang/LLVM from source", lambda: run_installer("clang_installer.py", "Building and installing Clang/LLVM", ["install"], 3600)),
    "ollama": ("Installing/updating Ollama", update_ollama),
    "ollama-models": ("Check and update Ollama models", update_ollama_models),
    "android-studio": ("Update Android Studio", lambda: run_installer("android_studio_updater.py", "Updating Android Studio")),
    "vscode": ("Updating VS Code (direct download)", update_vscode),
    "java": ("Updating Java JDK", update_java),
    "gradle": ("Updating Gradle via SDKMAN", update_gradle),
    "adb": ("Updating ADB/platform-tools", update_adb),
    "agp": ("Updating Android Gradle Plugin", update_agp),
}

LINUX_DEFAULT_ORDER = ["clang", "apt", "vscode", "node", "npm", "conda", "flatpak", "snap", "calibre", "tmux", "ptyxis", "alacritty", "foot", "ollama", "ollama-models", "android-studio", "java", "gradle", "adb", "agp"]

# Ubuntu/Debian - full desktop with apt
UBUNTU_UPDATE_TASKS = LINUX_UPDATE_TASKS
UBUNTU_DEFAULT_ORDER = LINUX_DEFAULT_ORDER

# Arch Linux - headless server, no GUI apps, no apt-dependent tasks
ARCH_UPDATE_TASKS = {
    "pacman": ("Updating pacman packages", update_pacman),
    # Arch: npm global without sudo (user prefix or pacman-managed)
    "npm": ("Updating npm global packages", lambda: run_command(
        "npm outdated -g; npm update -g 2>/dev/null || true",
        "Updating npm global packages"
    )),
    "conda": LINUX_UPDATE_TASKS["conda"],
    "ollama": LINUX_UPDATE_TASKS["ollama"],
    "ollama-models": LINUX_UPDATE_TASKS["ollama-models"],
    "tmux": LINUX_UPDATE_TASKS["tmux"],
}
ARCH_DEFAULT_ORDER = ["pacman", "npm", "conda", "ollama", "ollama-models", "tmux"]

# Termux - mobile, minimal (already defined above)
# TERMUX_UPDATE_TASKS, TERMUX_DEFAULT_ORDER

# Select tasks based on environment
if IS_TERMUX:
    UPDATE_TASKS, DEFAULT_ORDER = TERMUX_UPDATE_TASKS, TERMUX_DEFAULT_ORDER
elif IS_ARCH:
    UPDATE_TASKS, DEFAULT_ORDER = ARCH_UPDATE_TASKS, ARCH_DEFAULT_ORDER
else:  # Ubuntu/Debian/other Linux
    UPDATE_TASKS, DEFAULT_ORDER = UBUNTU_UPDATE_TASKS, UBUNTU_DEFAULT_ORDER


def run_task(task):
    """Run a single task and return (task_name, success)."""
    print(f"\n{'='*50}\n[{task}] {UPDATE_TASKS[task][0]}\n{'='*50}")
    return task, UPDATE_TASKS[task][1]()


def main():
    env_name = "Termux" if IS_TERMUX else ("Arch" if IS_ARCH else "Linux")
    p = argparse.ArgumentParser(description=f"System update script ({env_name})",
        epilog=f"Tasks: {', '.join(DEFAULT_ORDER)}")
    p.add_argument("tasks", nargs="*", metavar="TASK", help="Tasks to run (or 'all')")
    p.add_argument("-p", "--parallel", type=int, metavar="N", help="Run N tasks in parallel")
    if not IS_TERMUX:
        p.add_argument("--store-password", action="store_true", help="Store sudo password in keyring")
    args = p.parse_args()

    if not IS_TERMUX and getattr(args, 'store_password', False):
        return 0 if store_sudo_password() else 1

    tasks = DEFAULT_ORDER if not args.tasks or "all" in args.tasks else args.tasks
    invalid = [t for t in tasks if t not in UPDATE_TASKS]
    if invalid:
        return print(f"Unknown: {', '.join(invalid)}. Available: {', '.join(DEFAULT_ORDER)}", file=sys.stderr) or 1

    print(f"{'Termux' if IS_TERMUX else 'System'} updates: {', '.join(tasks)}" +
          ("" if IS_TERMUX or init_sudo() else " (Tip: --store-password)"))

    if args.parallel:
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            list(executor.map(run_task, tasks))
    else:
        for task in tasks:
            run_task(task)

    print("\n" + "="*50)
    if failed_updates:
        print(f"Completed with {len(failed_updates)} failure(s): {', '.join(failed_updates)}")
        return 1
    print("All updates completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
