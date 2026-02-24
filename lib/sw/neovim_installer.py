#!/usr/bin/env python3
"""
Neovim Installer and Configurer
Installs Neovim from source and sets up configuration with:
- LazyVim base
- Smooth scrolling
- Insert mode by default
"""

import subprocess
import os
import shutil
from pathlib import Path


def run(cmd, cwd=None, check=True):
    """Run a shell command, using stored sudo password if available."""
    print(f">>> {cmd}")
    pw = os.environ.get("SUDO_PW")
    if cmd.strip().startswith("sudo ") and pw:
        result = subprocess.run(cmd.replace("sudo ", "sudo -S ", 1), shell=True, cwd=cwd, check=False, input=pw, text=True, capture_output=True)
    else:
        result = subprocess.run(cmd, shell=True, cwd=cwd, check=False, capture_output=True, text=True)
    if result.returncode != 0 and check:
        if "Authentication failed" in (result.stderr or ""):
            raise subprocess.CalledProcessError(result.returncode, cmd, output="Sudo auth failed. Run 'sudo -v' first or use --store-password")
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stderr or result.stdout)
    return result


def install_dependencies():
    """Install build dependencies for Neovim."""
    print("\n=== Installing build dependencies ===")

    # Detect package manager
    if shutil.which("apt"):
        run("sudo apt-get update || true", check=False)
        run("sudo apt-get install -y ninja-build gettext cmake unzip curl build-essential git")
    elif shutil.which("dnf"):
        run("sudo dnf install -y ninja-build cmake gcc make unzip gettext curl git")
    elif shutil.which("pacman"):
        run("sudo pacman -S --noconfirm base-devel cmake unzip ninja curl git")
    elif shutil.which("brew"):
        run("brew install ninja cmake gettext curl git")
    else:
        print("Unknown package manager. Please install: ninja, cmake, gettext, curl, git")
        return False
    return True


def clone_neovim(build_dir):
    """Clone Neovim repository."""
    print("\n=== Cloning Neovim ===")

    if build_dir.exists():
        print(f"Removing existing {build_dir}")
        try: shutil.rmtree(build_dir)
        except PermissionError: run(f"sudo rm -rf {build_dir}")

    run(f"git clone --depth 1 https://github.com/neovim/neovim.git {build_dir}")
    return True


def build_neovim(build_dir):
    """Build Neovim from source."""
    print("\n=== Building Neovim ===")

    run("make CMAKE_BUILD_TYPE=Release", cwd=build_dir)
    return True


def install_neovim(build_dir):
    """Install Neovim system-wide."""
    print("\n=== Installing Neovim ===")

    run("sudo make install", cwd=build_dir)
    return True


def setup_lazyvim(config_dir):
    """Set up LazyVim starter configuration."""
    print("\n=== Setting up LazyVim ===")

    # Backup existing config
    if config_dir.exists():
        backup = config_dir.with_name("nvim.bak")
        if backup.exists():
            shutil.rmtree(backup)
        print(f"Backing up existing config to {backup}")
        shutil.move(config_dir, backup)

    # Clone LazyVim starter
    run(f"git clone https://github.com/LazyVim/starter {config_dir}")

    # Remove .git so user can make it their own
    git_dir = config_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)

    return True


def configure_options(config_dir):
    """Configure Neovim options."""
    print("\n=== Configuring options ===")

    options_file = config_dir / "lua" / "config" / "options.lua"

    options_content = '''\
-- Options are automatically loaded before lazy.nvim startup
-- Default options that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/options.lua
-- Add any additional options here

-- Enable mouse support
vim.opt.mouse = "a"
vim.opt.mousemodel = "extend"

-- Netrw settings for 2-panel layout
vim.g.netrw_banner = 0
vim.g.netrw_liststyle = 3
vim.g.netrw_browse_split = 4
vim.g.netrw_altv = 1
vim.g.netrw_winsize = 25

-- Fix: wipe netrw buffers when hidden to prevent extra panels
vim.api.nvim_create_autocmd("FileType", {
  pattern = "netrw",
  callback = function()
    vim.opt_local.bufhidden = "wipe"
  end,
})

-- Smooth scrolling
vim.opt.smoothscroll = true

-- Start in insert mode by default (for regular file buffers)
vim.api.nvim_create_autocmd("BufEnter", {
  callback = function(args)
    local bufnr = args.buf
    -- Defer to let buffer properties settle
    vim.schedule(function()
      -- Make sure we're still in the same buffer
      if vim.api.nvim_get_current_buf() ~= bufnr then
        return
      end
      -- Only enter insert mode if buffer is modifiable, normal type, and a real file
      local bo = vim.bo[bufnr]
      if bo.modifiable and bo.buftype == "" and vim.fn.buflisted(bufnr) == 1 then
        pcall(vim.cmd, "startinsert")
      end
    end)
  end,
})
'''

    options_file.write_text(options_content)
    print(f"Written: {options_file}")
    return True


def configure_plugins(config_dir):
    """Configure LazyVim plugins."""
    print("\n=== Configuring plugins ===")
    plugins_dir = config_dir / "lua" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    # Disable neo-tree
    (plugins_dir / "neo-tree.lua").write_text('return { { "nvim-neo-tree/neo-tree.nvim", enabled = false } }\n')
    print("Disabled neo-tree")
    return True


def add_shell_aliases():
    """Add helpful shell aliases."""
    print("\n=== Adding shell aliases ===")

    aliases = '''
# Neovim aliases
alias nv='nvim'
alias nve='nvim +"Lex"'
'''

    bashrc = Path.home() / ".bashrc"

    if bashrc.exists():
        content = bashrc.read_text()
        if "alias nv=" not in content:
            with open(bashrc, "a") as f:
                f.write(aliases)
            print(f"Added aliases to {bashrc}")
        else:
            print("Aliases already exist in .bashrc")

    return True


def verify_installation():
    """Verify Neovim installation."""
    print("\n=== Verifying installation ===")

    result = subprocess.run("nvim --version", shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        version_line = result.stdout.split('\n')[0]
        print(f"Installed: {version_line}")
        return True
    else:
        print("Neovim installation failed!")
        return False


def check_nvim_installed():
    """Check if Neovim is already installed."""
    result = subprocess.run("nvim --version", shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        version_line = result.stdout.split('\n')[0]
        return True, version_line
    return False, None


def launch_nvim(directory=None):
    """Launch Neovim in the specified directory (or current directory)."""
    target_dir = directory or os.getcwd()

    installed, version = check_nvim_installed()
    if not installed:
        print("Error: Neovim is not installed!")
        return 1

    subprocess.call(["nvim"], cwd=target_dir)
    return 0


def show_menu():
    """Show installation mode menu."""
    print("\n" + "=" * 50)
    print("Neovim Installer - Select Mode")
    print("=" * 50)
    print()
    print("  1. Full Install    - Build Neovim from source + LazyVim setup")
    print("  2. LazyVim Setup   - Configure LazyVim only (nvim must be installed)")
    print("  3. Run Neovim      - Launch nvim in current directory")
    print("  4. Exit")
    print()

    while True:
        choice = input("Select mode [1-4]: ").strip()
        if choice in ["1", "2", "3", "4"]:
            return int(choice)
        print("Invalid choice. Enter 1, 2, 3, or 4.")


def run_lazyvim_setup():
    """Run LazyVim setup only (no Neovim build)."""
    print("\n" + "=" * 50)
    print("LazyVim Setup Mode")
    print("=" * 50)

    # Check if nvim is installed
    installed, version = check_nvim_installed()
    if not installed:
        print("\nError: Neovim is not installed!")
        print("Please install Neovim first or use 'Full Install' mode.")
        return 1

    print(f"\nFound: {version}")

    config_dir = Path.home() / ".config" / "nvim"

    steps = [
        ("Setup LazyVim", lambda: setup_lazyvim(config_dir)),
        ("Configure options", lambda: configure_options(config_dir)),
        ("Configure plugins", lambda: configure_plugins(config_dir)),
        ("Add shell aliases", lambda: add_shell_aliases()),
    ]

    for name, step in steps:
        print(f"\n{'=' * 50}")
        print(f"Step: {name}")
        print("=" * 50)

        try:
            if not step():
                print(f"Step '{name}' failed!")
                return 1
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {e.output or e}")
            return 1

    print("\n" + "=" * 50)
    print("LazyVim Setup Complete!")
    print("=" * 50)
    print("\nNext steps:\n1. Restart your terminal (or run: source ~/.bashrc)\n2. Run 'nvim' to let LazyVim install plugins")
    return 0


def run_full_install():
    """Run the full installation process."""
    print("=" * 50)
    print("Full Neovim Install Mode")
    print("=" * 50)

    build_dir = Path.home() / "neovim-build"
    config_dir = Path.home() / ".config" / "nvim"

    steps = [
        ("Install dependencies", lambda: install_dependencies()),
        ("Clone Neovim", lambda: clone_neovim(build_dir)),
        ("Build Neovim", lambda: build_neovim(build_dir)),
        ("Install Neovim", lambda: install_neovim(build_dir)),
        ("Setup LazyVim", lambda: setup_lazyvim(config_dir)),
        ("Configure options", lambda: configure_options(config_dir)),
        ("Configure plugins", lambda: configure_plugins(config_dir)),
        ("Add shell aliases", lambda: add_shell_aliases()),
        ("Verify installation", lambda: verify_installation()),
    ]

    for name, step in steps:
        print(f"\n{'=' * 50}")
        print(f"Step: {name}")
        print("=" * 50)

        try:
            if not step():
                print(f"Step '{name}' failed!")
                return 1
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {e.output or e}")
            return 1

    print("\n" + "=" * 50)
    print("Installation complete!")
    print("=" * 50)
    print("\nNext steps:\n1. Restart your terminal (or run: source ~/.bashrc)\n2. Run 'nvim' to let LazyVim install plugins")

    # Cleanup
    if build_dir.exists():
        print(f"\nCleanup: Remove {build_dir} to save space (~500MB)")

    return 0


def main():
    """Main entry point with mode selection."""
    import sys

    # Check for command-line argument for non-interactive mode
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["--lazyvim", "-l", "lazyvim", "2"]:
            return run_lazyvim_setup()
        elif arg in ["--full", "-f", "full", "1"]:
            return run_full_install()
        elif arg in ["--run", "-r", "run", "3"]:
            # Optional second arg for directory
            directory = sys.argv[2] if len(sys.argv) > 2 else None
            return launch_nvim(directory)
        elif arg in ["--help", "-h"]:
            print("Usage: neovim_installer.py [option] [directory]")
            print()
            print("Options:")
            print("  --lazyvim, -l    LazyVim setup only (requires nvim installed)")
            print("  --full, -f       Full install (build from source + LazyVim)")
            print("  --run, -r        Run nvim in current dir (or specified directory)")
            print("  --help, -h       Show this help message")
            print()
            print("Run without arguments for interactive menu.")
            return 0

    # Interactive mode
    choice = show_menu()

    if choice == 1:
        return run_full_install()
    elif choice == 2:
        return run_lazyvim_setup()
    elif choice == 3:
        return launch_nvim()
    else:
        print("Exiting.")
        return 0


if __name__ == "__main__":
    exit(main())
