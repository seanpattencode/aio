#!/usr/bin/env python3
"""
Mamba/Micromamba manager with ZERO shell startup overhead.

Why:
Ai agents are trained on older tutorials and lts versions of linux often 
for single tasks in virtual sessions. They pip install and python python.py
not facilitating this slows down agent work. Having multiple projects
for a few projects with multiple deps is annoying, having hundreds or more
projects makes global installs needed. 
Micromamba is better than mamba but is less good by default of being
the drop in replacement for python due to pip not being there.
Its also important to just keep up to date with new python versions.
This script exists for these reasons.
We should not be going backwards in update speed, dev time in new repo,
ease of use in python.
for this reason i choose to use the python betas even though things break
for those fewer that break, the simplest soluition is a diff env
its worse to be behind than it is for your software to break that requires a simple lllm fix

Goal: python/mamba/micromamba work instantly without slowing down shell startup.
Approach: Add bin to PATH directly, lazy-load full init only when needed.

Benchmark with: python mamba_manager.py bench --clean  (baseline, no mamba)
                python mamba_manager.py bench          (with lazy-load, should match baseline)
"""
import os, subprocess, time, urllib.request, re, shutil, argparse
from pathlib import Path

# Installation paths
MAMBA_DIR = Path.home() / "miniforge3"
MICROMAMBA_DIR = Path.home() / "micromamba"
MICROMAMBA_BIN = Path.home() / ".local/bin/micromamba"

BASHRC = Path.home() / ".bashrc"
ZSHRC = Path.home() / ".zshrc"
MARKER = "# >>> mamba_manager lazy-load >>>"
MARKER_END = "# <<< mamba_manager lazy-load <<<"

def detect_backend() -> str:
    """Detect which backend is installed: 'micromamba', 'mamba', or None."""
    if MICROMAMBA_BIN.exists() or shutil.which("micromamba"):
        return "micromamba"
    if (MAMBA_DIR / "bin/mamba").exists():
        return "mamba"
    return None

def get_install_dir(backend: str) -> Path:
    return MICROMAMBA_DIR if backend == "micromamba" else MAMBA_DIR

def get_default_env_file(backend: str) -> Path:
    return get_install_dir(backend) / ".default_env"

def get_env_bin(backend: str, env_name: str = None) -> Path:
    base = get_install_dir(backend)
    if env_name and env_name != "base":
        return base / "envs" / env_name / "bin"
    # Both mamba and micromamba put base env at root prefix /bin
    return base / "bin"

def get_default_env(backend: str) -> str:
    f = get_default_env_file(backend)
    return f.read_text().strip() if f.exists() else "base"

def set_default_env(backend: str, env_name: str):
    get_default_env_file(backend).write_text(env_name)

def is_installed(backend: str = None) -> bool:
    if backend == "micromamba":
        return MICROMAMBA_BIN.exists() or shutil.which("micromamba")
    elif backend == "mamba":
        return (MAMBA_DIR / "etc/profile.d/conda.sh").exists()
    return detect_backend() is not None

def install_micromamba():
    """Install micromamba - single static binary."""
    if is_installed("micromamba"):
        print(f"Micromamba already installed")
        return True

    print("Installing micromamba...")
    MICROMAMBA_BIN.parent.mkdir(parents=True, exist_ok=True)

    # Download and extract
    arch = os.uname().machine
    if arch == "x86_64":
        arch = "64"
    url = f"https://micro.mamba.pm/api/micromamba/linux-{arch}/latest"

    try:
        subprocess.run(
            f'curl -Ls {url} | tar -xvj -C {MICROMAMBA_BIN.parent} bin/micromamba --strip-components=1',
            shell=True, check=True
        )
        # Create base env with python
        MICROMAMBA_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            str(MICROMAMBA_BIN), "create", "-y", "-r", str(MICROMAMBA_DIR),
            "-n", "base", "-c", "conda-forge", "python", "pip"
        ], check=True)
        print(f"Installed micromamba to {MICROMAMBA_BIN}")
        return True
    except Exception as e:
        print(f"Install failed: {e}")
        return False

def create_ml_env():
    """Create ML environment with stable Python + PyTorch for libs that don't support beta."""
    if not is_installed("micromamba"):
        print("Micromamba not installed. Run: install")
        return False

    env_path = MICROMAMBA_DIR / "envs" / "ml"
    if env_path.exists():
        print(f"ML env already exists at {env_path}")
        return True

    print("Creating ML environment with stable Python + PyTorch...")
    print("This may take a few minutes (PyTorch is large)...", flush=True)

    # Use latest stable Python (not beta) + PyTorch from pytorch channel
    subprocess.run([
        str(MICROMAMBA_BIN), "create", "-y", "-r", str(MICROMAMBA_DIR),
        "-n", "ml", "-c", "pytorch", "-c", "conda-forge",
        "python=3.13", "pip", "pytorch", "torchvision", "torchaudio"
    ], check=True)

    print(f"Created ML env. Use: micromamba run -n ml python script.py")
    return True

def install_mamba():
    """Install miniforge/mamba."""
    if is_installed("mamba"):
        print(f"Mamba already installed at {MAMBA_DIR}")
        return True

    installer = Path("/tmp/Miniforge3.sh")
    url = f"https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-{os.uname().sysname}-{os.uname().machine}.sh"
    print(f"Downloading {url}")
    urllib.request.urlretrieve(url, installer)
    subprocess.run(["bash", str(installer), "-b", "-p", str(MAMBA_DIR)], check=True)
    installer.unlink()
    print(f"Installed mamba to {MAMBA_DIR}")
    return True

def upgrade(backend: str, env_name: str = "base"):
    """Upgrade Python and pip to latest versions."""
    if not is_installed(backend):
        print(f"{backend} not installed")
        return False

    if backend == "micromamba":
        cmd = [str(MICROMAMBA_BIN), "update", "-y", "-n", env_name, "-c", "conda-forge", "python", "pip"]
    else:
        cmd = [str(MAMBA_DIR / "bin/mamba"), "update", "-y", "-n", env_name, "-c", "conda-forge", "python", "pip"]

    print(f"Upgrading python and pip in {env_name}...", flush=True)
    result = subprocess.run(cmd)
    return result.returncode == 0

def uninstall(backend: str):
    """Remove installation."""
    if backend == "micromamba":
        if MICROMAMBA_BIN.exists():
            MICROMAMBA_BIN.unlink()
        if MICROMAMBA_DIR.exists():
            shutil.rmtree(MICROMAMBA_DIR)
    else:
        if MAMBA_DIR.exists():
            shutil.rmtree(MAMBA_DIR)
    unpersist()
    print(f"Removed {backend}")

def lazy_block_micromamba(env_name: str = "base") -> str:
    """Zero-overhead lazy-load block for micromamba."""
    env_bin = get_env_bin("micromamba", env_name)
    return f'''{MARKER}
# Goal: 0ms shell overhead. Python works via PATH, micromamba lazy-loads on first use.
export PATH="{env_bin}:$PATH"
export MAMBA_ROOT_PREFIX="{MICROMAMBA_DIR}"
micromamba() {{
    unset -f micromamba
    eval "$(command {MICROMAMBA_BIN} shell hook --shell bash)"
    command micromamba "$@"
}}
{MARKER_END}'''

def lazy_block_mamba(env_name: str = "base") -> str:
    """Zero-overhead lazy-load block for mamba/conda."""
    env_bin = get_env_bin("mamba", env_name)
    return f'''{MARKER}
# Goal: 0ms shell overhead. Python works via PATH, mamba/conda lazy-load on first use.
export PATH="{env_bin}:$PATH"
__mamba_load() {{
    unset -f conda mamba __mamba_load
    export MAMBA_ROOT_PREFIX="{MAMBA_DIR}"
    source "{MAMBA_DIR}/etc/profile.d/conda.sh"
    source "{MAMBA_DIR}/etc/profile.d/mamba.sh"
}}
conda() {{ __mamba_load && conda "$@"; }}
mamba() {{ __mamba_load && mamba "$@"; }}
{MARKER_END}'''

def lazy_block(backend: str, env_name: str = "base") -> str:
    if backend == "micromamba":
        return lazy_block_micromamba(env_name)
    return lazy_block_mamba(env_name)

def is_persisted() -> bool:
    return BASHRC.exists() and MARKER in BASHRC.read_text()

def persist(backend: str, env_name: str = None):
    """Add lazy-loading to shell rc files (zero startup penalty)."""
    env = env_name or get_default_env(backend)
    env_bin = get_env_bin(backend, env)

    if not env_bin.exists():
        print(f"Environment '{env}' not found at {env_bin}")
        return False

    if env != "base":
        set_default_env(backend, env)

    if is_persisted():
        unpersist()

    block = lazy_block(backend, env)
    for rc in [BASHRC, ZSHRC]:
        if rc.exists():
            with open(rc, "a") as f:
                f.write("\n" + block + "\n")
            print(f"Added to {rc}")

    return True

def unpersist():
    """Remove lazy-loading from shell rc files."""
    for rc in [BASHRC, ZSHRC]:
        if rc.exists() and MARKER in rc.read_text():
            txt = rc.read_text()
            txt = re.sub(rf'\n?{re.escape(MARKER)}.*?{re.escape(MARKER_END)}\n?', '', txt, flags=re.DOTALL)
            rc.write_text(txt)
            print(f"Removed from {rc}")

def bench_shell(n: int = 5, clean: bool = False) -> float:
    """Benchmark shell startup time in ms. If clean=True, measure without any mamba config."""
    times = []
    env = os.environ.copy()

    if clean:
        # Create minimal bashrc without mamba
        tmp_rc = Path("/tmp/bashrc_clean")
        if BASHRC.exists():
            txt = BASHRC.read_text()
            txt = re.sub(rf'\n?{re.escape(MARKER)}.*?{re.escape(MARKER_END)}\n?', '', txt, flags=re.DOTALL)
            # Also remove standard conda init
            txt = re.sub(r'\n?# >>> conda initialize >>>.*?# <<< conda initialize <<<\n?', '', txt, flags=re.DOTALL)
            tmp_rc.write_text(txt)
        else:
            tmp_rc.write_text("")
        env["HOME"] = "/tmp"
        env["BASH_ENV"] = ""
        # Use temp bashrc
        cmd = ["bash", "--rcfile", str(tmp_rc), "-ic", "exit"]
    else:
        cmd = ["bash", "-ic", "exit"]

    # Warmup
    subprocess.run(cmd, capture_output=True, env=env)

    for _ in range(n):
        t = time.perf_counter()
        subprocess.run(cmd, capture_output=True, env=env)
        times.append((time.perf_counter() - t) * 1000)

    return sum(times) / n

def info(backend: str = None):
    """Display environment info."""
    backend = backend or detect_backend()
    if not backend:
        print("No mamba/micromamba installed")
        return

    install_dir = get_install_dir(backend)
    which_py = subprocess.run(
        ["bash", "-ic", "which python 2>/dev/null"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    ).stdout.strip()

    print(f"Backend: {backend}")
    print(f"Install dir: {install_dir}")
    print(f"Default env: {get_default_env(backend)}")
    print(f"Persisted: {is_persisted()}")
    print(f"Active python: {which_py or 'system'}")

    # List envs
    print(f"\nEnvironments:")
    envs_dir = install_dir / "envs"
    if backend == "mamba":
        envs = [("base", install_dir / "bin/python")]
    else:
        envs = []

    if envs_dir.exists():
        envs += [(d.name, d / "bin/python") for d in sorted(envs_dir.iterdir()) if d.is_dir()]

    for name, py in envs:
        if py.exists():
            ver = subprocess.run(
                [str(py), "-c", "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True
            ).stdout.strip()
            active = "*" if which_py and Path(which_py).resolve() == py.resolve() else " "
            print(f"  {active} {name:15} Python {ver}")
        else:
            print(f"    {name:15} (no python)")

def main():
    p = argparse.ArgumentParser(
        description="Mamba/Micromamba manager with zero shell overhead",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s install              # Install micromamba (default)
  %(prog)s install --mamba      # Install mamba instead
  %(prog)s ml                   # Create ML env (stable Python + PyTorch)
  %(prog)s upgrade              # Upgrade python/pip to latest
  %(prog)s persist              # Add to .bashrc with 0 overhead
  %(prog)s bench                # Measure shell startup time
  %(prog)s bench --clean        # Baseline without mamba (compare to confirm 0 overhead)
"""
    )
    p.add_argument("command", nargs="?", default="status",
                   choices=["install", "uninstall", "ml", "upgrade", "persist", "unpersist", "info", "bench", "status"],
                   help="Command to run")
    p.add_argument("--mamba", action="store_true", help="Use mamba/miniforge instead of micromamba")
    p.add_argument("--env", "-e", default=None, help="Environment name (default: base)")
    p.add_argument("--clean", action="store_true", help="For bench: measure without mamba config")
    p.add_argument("-n", type=int, default=5, help="Bench iterations")
    args = p.parse_args()

    # Determine backend
    backend = "mamba" if args.mamba else "micromamba"
    detected = detect_backend()

    if args.command == "install":
        print(f"Shell startup before: {bench_shell():.1f}ms")
        if backend == "micromamba":
            if not install_micromamba():
                return 1
        else:
            if not install_mamba():
                return 1
        persist(backend, args.env)
        print(f"Shell startup after:  {bench_shell():.1f}ms")
        print(f"\nRestart shell or: source ~/.bashrc")

    elif args.command == "uninstall":
        b = detected or backend
        if not is_installed(b):
            print("Nothing installed")
            return 1
        uninstall(b)

    elif args.command == "ml":
        if not create_ml_env():
            return 1

    elif args.command == "upgrade":
        b = detected or backend
        if not upgrade(b, args.env or "base"):
            return 1

    elif args.command == "persist":
        b = detected or backend
        if not is_installed(b):
            print(f"{b} not installed. Run: install")
            return 1
        print(f"Shell startup before: {bench_shell():.1f}ms")
        persist(b, args.env)
        print(f"Shell startup after:  {bench_shell():.1f}ms")

    elif args.command == "unpersist":
        unpersist()

    elif args.command == "info":
        info(detected)

    elif args.command == "bench":
        if args.clean:
            clean_time = bench_shell(args.n, clean=True)
            print(f"Shell startup (clean, no mamba): {clean_time:.1f}ms")
        current_time = bench_shell(args.n, clean=False)
        print(f"Shell startup (current):          {current_time:.1f}ms")
        if args.clean:
            overhead = current_time - clean_time
            print(f"Overhead:                         {overhead:+.1f}ms {'(good!)' if abs(overhead) < 5 else '(check config)'}")

    else:  # status
        if detected:
            print(f"Installed: {detected}")
            print(f"Path: {get_install_dir(detected)}")
            print(f"Persisted: {is_persisted()}")
            print(f"Default env: {get_default_env(detected)}")
        else:
            print("Not installed")
            print(f"\nTo install: {__file__} install [--mamba]")

    return 0

if __name__ == "__main__":
    exit(main())
