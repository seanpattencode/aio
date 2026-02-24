#!/usr/bin/env python3
"""Clang/LLVM Installer - builds from source with native optimizations.

Builds latest stable Clang/LLVM from GitHub. Installs to /usr/local so it
coexists with the system apt version.
  - Binary: /usr/local/bin/clang (takes priority over /usr/bin/clang via PATH)
  - Includes: clang, clang++, clang-tools-extra, lld
  - Only builds X86 target (native machine)
"""
import subprocess, os, shutil, sys, re
from pathlib import Path

BUILD_DIR = Path.home() / "llvm-build"
SRC_DIR = BUILD_DIR / "llvm-project"
CMAKE_BUILD_DIR = BUILD_DIR / "build"
INSTALL_PREFIX = "/usr/local"
BIN_PATH = f"{INSTALL_PREFIX}/bin/clang"

def run(cmd, cwd=None, check=True, env=None):
    print(f">>> {cmd}")
    inp = None
    if cmd.strip().startswith("sudo ") and (pw := os.environ.get("SUDO_PW")):
        cmd = cmd.replace("sudo ", "sudo -S ", 1)
        inp = pw
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check,
                          input=inp, text=True if inp else None, env=env)

def get_version(binary="clang"):
    """Get version from a clang binary."""
    path = shutil.which(binary)
    if not path:
        return None
    r = subprocess.run(f"{path} --version", shell=True, capture_output=True, text=True)
    m = re.search(r'clang version ([\d.]+)', r.stdout)
    return m.group(1) if m else None

def get_source_version():
    """Get version from the /usr/local/bin/clang build."""
    if not Path(BIN_PATH).exists():
        return None
    r = subprocess.run(f"{BIN_PATH} --version", shell=True, capture_output=True, text=True)
    m = re.search(r'clang version ([\d.]+)', r.stdout)
    return m.group(1) if m else None

def get_latest_tag():
    """Get the latest stable release tag from the cloned repo."""
    r = subprocess.run(
        "git tag -l 'llvmorg-*' --sort=-version:refname | grep -v rc | head -1",
        shell=True, cwd=SRC_DIR, capture_output=True, text=True
    )
    return r.stdout.strip() if r.returncode == 0 else None

def install_deps():
    """Install build dependencies."""
    if shutil.which("apt"):
        run("sudo apt update", check=False)
        run("sudo apt install -y cmake ninja-build build-essential python3 git "
            "libxml2-dev zlib1g-dev libzstd-dev binutils-dev")
    elif shutil.which("dnf"):
        run("sudo dnf install -y cmake ninja-build gcc gcc-c++ python3 git "
            "libxml2-devel zlib-devel libzstd-devel binutils-devel")
    elif shutil.which("pacman"):
        run("sudo pacman -S --noconfirm cmake ninja gcc python git libxml2 zlib zstd binutils")
    else:
        print("Unknown package manager")
        return False
    return True

def cmake_configure(tag):
    """Run CMake configure step."""
    # Use system clang to bootstrap if available, else gcc
    cc = shutil.which("clang") or "gcc"
    cxx = shutil.which("clang++") or "g++"

    cmake_cmd = [
        "cmake", "-G", "Ninja",
        "-S", str(SRC_DIR / "llvm"), "-B", str(CMAKE_BUILD_DIR),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={INSTALL_PREFIX}",
        "-DLLVM_ENABLE_PROJECTS=clang;clang-tools-extra;lld",
        "-DLLVM_TARGETS_TO_BUILD=X86",
        "-DLLVM_USE_LINKER=lld",
        "-DLLVM_PARALLEL_LINK_JOBS=2",
        f"-DCMAKE_C_COMPILER={cc}",
        f"-DCMAKE_CXX_COMPILER={cxx}",
        "-DCMAKE_C_FLAGS=-march=native",
        "-DCMAKE_CXX_FLAGS=-march=native",
        "-DLLVM_OPTIMIZED_TABLEGEN=ON",
        "-DLLVM_ENABLE_ZSTD=ON",
        "-DLLVM_BINUTILS_INCDIR=/usr/include",
        "-DLLVM_ENABLE_RUNTIMES=compiler-rt",
        "-DCOMPILER_RT_BUILD_SANITIZERS=ON",
        "-DCOMPILER_RT_BUILD_XRAY=OFF",
        "-DCOMPILER_RT_BUILD_LIBFUZZER=OFF",
        "-DCOMPILER_RT_BUILD_PROFILE=OFF",
        "-DCOMPILER_RT_BUILD_MEMPROF=OFF",
        "-DCOMPILER_RT_BUILD_ORC=OFF",
    ]
    # Delete cmake cache to force fresh config (cached values override -D flags)
    cache = CMAKE_BUILD_DIR / "CMakeCache.txt"
    if cache.exists():
        cache.unlink()
    print(f">>> cmake {' '.join(cmake_cmd[1:])}")
    subprocess.run(cmake_cmd, check=True)

def fix_sanitizer_ignorelists():
    """Copy sanitizer ignorelist files that ninja install misses.

    compiler-rt builds these into the build tree but the install target
    doesn't always copy them to <prefix>/lib/clang/<ver>/share/.
    Without them, -fsanitize=cfi fails with 'missing sanitizer ignorelist'.
    """
    # Detect clang version from the install prefix
    clang_lib = Path(INSTALL_PREFIX) / "lib" / "clang"
    if not clang_lib.exists():
        return
    versions = [d for d in clang_lib.iterdir() if d.is_dir()]
    if not versions:
        return
    ver_dir = versions[0]
    share_src = CMAKE_BUILD_DIR / "lib" / "clang" / ver_dir.name / "share"
    share_dst = ver_dir / "share"
    if not share_src.exists():
        return
    ignorelists = list(share_src.glob("*.txt"))
    if not ignorelists:
        return
    if share_dst.exists() and all((share_dst / f.name).exists() for f in ignorelists):
        return  # already installed
    run(f"sudo mkdir -p {share_dst}")
    for f in ignorelists:
        run(f"sudo cp {f} {share_dst}/{f.name}")
    print(f"Installed {len(ignorelists)} sanitizer ignorelist(s) to {share_dst}")

def needs_reconfigure():
    """Check if cmake cache differs from our desired config."""
    cache = CMAKE_BUILD_DIR / "CMakeCache.txt"
    if not cache.exists():
        return True
    text = cache.read_text()
    if "LLVM_BINUTILS_INCDIR:PATH=/usr/include" not in text:
        return True
    if "LLVM_TARGETS_TO_BUILD:STRING=X86" not in text:
        return True
    if "LLVM_ENABLE_RUNTIMES:STRING=compiler-rt" not in text:
        return True
    return False

def try_incremental():
    """Try incremental build. Returns True if successful, False to trigger full build."""
    if not (SRC_DIR / ".git").exists() or not CMAKE_BUILD_DIR.exists():
        return False
    print("=== Trying incremental build ===\n")
    try:
        install_deps()
        run("git fetch --tags --force", cwd=SRC_DIR)
        latest_tag = get_latest_tag()
        if not latest_tag:
            return False
        current = subprocess.run(
            "git describe --tags --exact-match HEAD 2>/dev/null",
            shell=True, cwd=SRC_DIR, capture_output=True, text=True
        )
        same_tag = current.stdout.strip() == latest_tag
        reconf = needs_reconfigure()
        if same_tag and not reconf:
            print(f"Already at {latest_tag}.")
            return True
        if not same_tag:
            print(f"Updating to {latest_tag}...")
            run(f"git checkout {latest_tag}", cwd=SRC_DIR)
        if reconf:
            print("Reconfiguring (cmake options changed)...")
        cmake_configure(latest_tag)
        run(f"ninja -C {CMAKE_BUILD_DIR}", check=True)
        run(f"sudo ninja -C {CMAKE_BUILD_DIR} install")
        fix_sanitizer_ignorelists()
        return True
    except Exception as e:
        print(f"Incremental build failed: {e}\nFalling back to full build...\n")
        return False

def install():
    print("=== Clang/LLVM (Source) Installer ===\n")

    # Try incremental first
    if try_incremental():
        if v := get_source_version():
            print(f"\n✓ Updated: clang {v}")
            return True

    # Install dependencies
    if not install_deps():
        return False

    # Full clean build
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)

    # Shallow clone + tags (full clone is ~2GB, shallow is ~500MB)
    run(f"git clone --depth 1 https://github.com/llvm/llvm-project.git {SRC_DIR}")
    run("git fetch --tags --force", cwd=SRC_DIR)

    # Checkout latest stable release
    latest_tag = get_latest_tag()
    if latest_tag:
        # Need to fetch that specific tag's commit
        run(f"git fetch --depth 1 origin tag {latest_tag}", cwd=SRC_DIR)
        run(f"git checkout {latest_tag}", cwd=SRC_DIR)
        print(f"Building {latest_tag}...")
    else:
        print("Building from main (no release tag found)...")

    # Configure
    cmake_configure(latest_tag)

    # Build (this will take a while - LLVM is large)
    run(f"ninja -C {CMAKE_BUILD_DIR}")

    # Install
    run(f"sudo ninja -C {CMAKE_BUILD_DIR} install")
    fix_sanitizer_ignorelists()

    # Verify
    if v := get_source_version():
        sys_ver = get_version() or "not installed"
        print(f"\n✓ Installed: clang {v}")
        print(f"  Binary: {BIN_PATH}")
        print(f"  System: clang {sys_ver}")
        print(f"  Test:   {BIN_PATH} --version")
        return True
    print("✗ Installation failed")
    return False

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install":
        sys.exit(0 if install() else 1)
    elif cmd in ("-h", "--help", "help"):
        print(f"Usage: {sys.argv[0]} [install|status]")
    else:
        src_ver = get_source_version()
        sys_ver = get_version()
        print(f"Clang (Source): {src_ver or 'not installed'}")
        if src_ver:
            print(f"  Binary: {BIN_PATH}")
        print(f"System: clang {sys_ver or 'not installed'}")
        print(f"\nCommands: install, status")
