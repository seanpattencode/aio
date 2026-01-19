#!/bin/bash
set -e

G='\033[32m' Y='\033[33m' C='\033[36m' R='\033[0m'
ok() { echo -e "${G}✓${R} $1"; }
info() { echo -e "${C}>${R} $1"; }
warn() { echo -e "${Y}!${R} $1"; }
die() { echo "✗ $1"; exit 1; }

BIN="$HOME/.local/bin"
mkdir -p "$BIN"
export PATH="$BIN:$PATH"

# Detect OS and root access
if [[ "$OSTYPE" == darwin* ]]; then OS=mac
elif [[ -f /data/data/com.termux/files/usr/bin/bash ]]; then OS=termux
elif [[ -f /etc/debian_version ]]; then OS=debian
elif [[ -f /etc/arch-release ]]; then OS=arch
elif [[ -f /etc/fedora-release ]]; then OS=fedora
else OS=unknown; fi

# Check root/sudo access
if [[ $EUID -eq 0 ]]; then SUDO=""
elif sudo -n true 2>/dev/null; then SUDO="sudo"
else SUDO=""; fi
info "Detected: $OS ${SUDO:+(sudo)}${SUDO:-"(no root)"}"

# Install node via fnm if no npm
install_fnm() {
    command -v npm &>/dev/null && return 0
    info "Installing fnm + node (user-level)..."
    curl -fsSL https://fnm.vercel.app/install | bash -s -- --skip-shell --install-dir "$BIN"
    export PATH="$BIN:$PATH"
    eval "$("$BIN/fnm" env --shell bash 2>/dev/null)" || true
    "$BIN/fnm" install --lts && ok "node $(node -v)" || warn "fnm install failed"
}

# Install system packages
case $OS in
    mac)
        command -v brew &>/dev/null || die "Install Homebrew first: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        brew install tmux node 2>/dev/null || brew upgrade tmux node 2>/dev/null || true
        ok "tmux + node"
        ;;
    debian)
        if [[ -n "$SUDO" ]]; then
            export DEBIAN_FRONTEND=noninteractive
            $SUDO apt-get update -qq
            $SUDO apt-get install -y -qq tmux git curl nodejs npm python3-pip 2>/dev/null || true
            ok "system packages"
        else install_fnm; command -v tmux &>/dev/null || warn "tmux needs: sudo apt install tmux"; fi
        ;;
    arch)
        if [[ -n "$SUDO" ]]; then $SUDO pacman -Sy --noconfirm tmux nodejs npm git python-pip 2>/dev/null && ok "system packages"
        else install_fnm; command -v tmux &>/dev/null || warn "tmux needs: sudo pacman -S tmux"; fi
        ;;
    fedora)
        if [[ -n "$SUDO" ]]; then $SUDO dnf install -y tmux nodejs npm git python3-pip 2>/dev/null && ok "system packages"
        else install_fnm; command -v tmux &>/dev/null || warn "tmux needs: sudo dnf install tmux"; fi
        ;;
    termux) pkg update -y && pkg install -y tmux nodejs git python && ok "system packages" ;;
    *) install_fnm; warn "Unknown OS - install tmux manually" ;;
esac

# Ensure fnm node in PATH
if [[ -f "$BIN/fnm" ]]; then eval "$("$BIN/fnm" env --shell bash 2>/dev/null)" || true; fi

# Node CLIs
install_cli() {
    local pkg="$1" cmd="$2"
    if ! command -v "$cmd" &>/dev/null; then
        info "Installing $cmd..."
        if command -v npm &>/dev/null; then
            npm install -g "$pkg" 2>&1 | tail -1 && ok "$cmd" || warn "$cmd failed"
        else
            warn "$cmd skipped (npm not found)"
        fi
    else
        ok "$cmd (exists)"
    fi
}

install_cli "@anthropic-ai/claude-code" "claude"
install_cli "@openai/codex" "codex"
install_cli "@google/gemini-cli" "gemini"

# Python extras (optional)
if command -v pip3 &>/dev/null; then pip3 install --user -q pexpect prompt_toolkit 2>/dev/null && ok "python extras"
elif command -v pip &>/dev/null; then pip install --user -q pexpect prompt_toolkit 2>/dev/null && ok "python extras"
elif command -v python3 &>/dev/null; then python3 -m ensurepip --user 2>/dev/null; python3 -m pip install --user -q pexpect prompt_toolkit 2>/dev/null && ok "python extras" || warn "pip not available"; fi

# aio itself
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/aio.py" ]]; then
    cp "$SCRIPT_DIR/aio.py" "$BIN/aio" && chmod +x "$BIN/aio" && ok "aio installed (local)"
else
    AIO_URL="https://raw.githubusercontent.com/seanpattencode/aio/main/aio.py"
    curl -fsSL "$AIO_URL" -o "$BIN/aio" && chmod +x "$BIN/aio" && ok "aio installed (remote)"
fi

# PATH setup in shell rc
RC="$HOME/.bashrc"; [[ -f "$HOME/.zshrc" ]] && RC="$HOME/.zshrc"
grep -q '.local/bin' "$RC" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
[[ -f "$BIN/fnm" ]] && grep -q 'fnm env' "$RC" 2>/dev/null || echo 'eval "$(~/.local/bin/fnm env 2>/dev/null)"' >> "$RC"

echo -e "\n${G}Done!${R} Run: source $RC && aio"
