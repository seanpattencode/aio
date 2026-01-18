#!/bin/bash
set -e

G='\033[32m' Y='\033[33m' C='\033[36m' R='\033[0m'
ok() { echo -e "${G}✓${R} $1"; }
info() { echo -e "${C}>${R} $1"; }
warn() { echo -e "${Y}!${R} $1"; }
die() { echo "✗ $1"; exit 1; }

BIN="$HOME/.local/bin"
mkdir -p "$BIN"

# Detect OS
if [[ "$OSTYPE" == darwin* ]]; then OS=mac
elif [[ -f /data/data/com.termux/files/usr/bin/bash ]]; then OS=termux
elif [[ -f /etc/debian_version ]]; then OS=debian
elif [[ -f /etc/arch-release ]]; then OS=arch
elif [[ -f /etc/fedora-release ]]; then OS=fedora
else OS=unknown; fi
info "Detected: $OS"

# Install system packages
case $OS in
    mac)
        command -v brew &>/dev/null || die "Install Homebrew first: https://brew.sh"
        brew install tmux node 2>/dev/null || brew upgrade tmux node 2>/dev/null || true
        ok "tmux + node"
        ;;
    debian)
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq tmux git curl ca-certificates unzip python3-pip 2>/dev/null || true
        # Install nodejs+npm from repos
        if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
            apt-get install -y -qq nodejs npm 2>/dev/null || true
        fi
        # Fallback: download node binary directly
        if ! command -v npm &>/dev/null; then
            info "Downloading node directly..."
            NODE_VER="v22.12.0"
            curl -fsSL "https://nodejs.org/dist/${NODE_VER}/node-${NODE_VER}-linux-x64.tar.xz" | tar -xJf - -C /usr/local --strip-components=1
        fi
        ok "tmux + node $(node -v 2>/dev/null || echo 'missing') + npm $(npm -v 2>/dev/null || echo 'missing')"
        ;;
    arch)
        pacman -Sy --noconfirm tmux nodejs npm git
        ok "tmux + node"
        ;;
    fedora)
        dnf install -y tmux nodejs npm git
        ok "tmux + node"
        ;;
    termux)
        pkg update -y && pkg install -y tmux nodejs git python
        ok "tmux + node"
        ;;
    *)
        warn "Unknown OS - install tmux and node manually"
        ;;
esac

# Ensure node/npm in PATH (for fnm)
if [[ -d "$HOME/.local/share/fnm" ]]; then
    export PATH="$HOME/.local/share/fnm:$PATH"
    eval "$(fnm env --shell bash 2>/dev/null)" || true
fi

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

# Python extras (optional, non-fatal)
if command -v python3 &>/dev/null; then
    python3 -m pip install --user -q pexpect prompt_toolkit aiohttp 2>/dev/null && ok "python extras" || true
fi

# aio itself
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/aio.py" ]]; then
    cp "$SCRIPT_DIR/aio.py" "$BIN/aio" && chmod +x "$BIN/aio" && ok "aio installed (local)"
else
    AIO_URL="https://raw.githubusercontent.com/seanpattencode/aio/main/aio.py"
    curl -fsSL "$AIO_URL" -o "$BIN/aio" && chmod +x "$BIN/aio" && ok "aio installed (remote)"
fi

# PATH check
if [[ ":$PATH:" != *":$BIN:"* ]]; then
    warn "Add to PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo -e "\n${G}Done!${R} Run: aio help"
