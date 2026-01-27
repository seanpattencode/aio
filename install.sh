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

# Check root/sudo access (only prompt if deps missing)
SUDO=""
if ! command -v tmux &>/dev/null || ! command -v npm &>/dev/null; then
    if [[ $EUID -eq 0 ]]; then SUDO=""
    elif sudo -n true 2>/dev/null; then SUDO="sudo"
    elif command -v sudo &>/dev/null && [[ -t 0 ]]; then info "sudo password needed for system packages"; sudo -v && SUDO="sudo"
    fi
fi
info "Detected: $OS ${SUDO:+(sudo)}${SUDO:-"(no root)"}"

# Install node to user space if no npm
install_node() {
    command -v npm &>/dev/null && return 0
    info "Installing node (user-level)..."
    ARCH=$(uname -m)
    [[ "$ARCH" == "x86_64" ]] && ARCH="x64"
    [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]] && ARCH="arm64"

    if [[ "$OSTYPE" == darwin* ]]; then
        # macOS
        curl -fsSL "https://nodejs.org/dist/v22.12.0/node-v22.12.0-darwin-$ARCH.tar.gz" | tar -xzf - -C "$HOME/.local" --strip-components=1
    else
        # Linux
        curl -fsSL "https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-$ARCH.tar.xz" | tar -xJf - -C "$HOME/.local" --strip-components=1
    fi
    command -v node &>/dev/null && ok "node $(node -v)" || warn "node install failed"
}

# Install system packages
case $OS in
    mac)
        command -v brew &>/dev/null || die "Install Homebrew first: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        brew tap hudochenkov/sshpass 2>/dev/null; brew install tmux node gh sshpass 2>/dev/null || brew upgrade tmux node gh sshpass 2>/dev/null || true
        ok "tmux + node + gh"
        ;;
    debian)
        if [[ -n "$SUDO" ]]; then
            export DEBIAN_FRONTEND=noninteractive
            $SUDO apt update -qq && $SUDO apt install -yqq tmux git curl nodejs npm python3-pip sshpass 2>/dev/null || true
            ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo apt install tmux"; fi
        ;;
    arch)
        if [[ -n "$SUDO" ]]; then $SUDO pacman -Sy --noconfirm tmux nodejs npm git python-pip sshpass 2>/dev/null && ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo pacman -S tmux"; fi
        ;;
    fedora)
        if [[ -n "$SUDO" ]]; then $SUDO dnf install -y tmux nodejs npm git python3-pip sshpass 2>/dev/null && ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo dnf install tmux"; fi
        ;;
    termux) pkg update -y && pkg install -y tmux nodejs git python openssh sshpass && ok "pkgs" ;;
    *) install_node; warn "Unknown OS - install tmux manually" ;;
esac

# aio itself (install early, before slow npm installs)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
AIO_URL="https://raw.githubusercontent.com/seanpattencode/aio/main/aio.py"
if [[ -f "$SCRIPT_DIR/aio.py" ]]; then
    ln -sf "$SCRIPT_DIR/aio.py" "$BIN/aio" && chmod +x "$BIN/aio" && ok "aio installed (local)"
    ln -sf "$SCRIPT_DIR/aio-i" "$BIN/aio-i" && chmod +x "$BIN/aio-i" && ok "aio-i installed (local)"
else
    curl -fsSL "$AIO_URL" -o "$BIN/aio" && chmod +x "$BIN/aio" && ok "aio installed (remote)"
    curl -fsSL "${AIO_URL%aio.py}aio-i" -o "$BIN/aio-i" && chmod +x "$BIN/aio-i" && ok "aio-i installed (remote)"
fi

# PATH setup in shell rc (do early so aio works immediately)
RC="$HOME/.bashrc"; [[ -f "$HOME/.zshrc" ]] && RC="$HOME/.zshrc"
grep -q '.local/bin' "$RC" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"

# Fast aio bash function (2ms startup vs 25ms python)
sed -i '/^aio() {/,/^}/d' "$RC" 2>/dev/null  # Remove old function
cat >> "$RC" << 'AIOFUNC'
aio() {
    local cache=~/.local/share/aios/help_cache.txt projects=~/.local/share/aios/projects.txt icache=~/.local/share/aios/i_cache.txt
    [[ "$1" == "a" || "$1" == "ai" || "$1" == "aio" || "$1" == "all" ]] && { command python3 ~/.local/bin/aio "$@"; return; }
    if [[ "$1" =~ ^[0-9]+$ ]]; then local dir=$(sed -n "$((${1}+1))p" "$projects" 2>/dev/null); [[ -d "$dir" ]] && { echo "📂 $dir"; cd "$dir"; return; }; fi
    local d="${1/#~/$HOME}"; [[ "$1" == /projects/* ]] && d="$HOME$1"; [[ -d "$d" ]] && { echo "📂 $d"; cd "$d"; ls; return; }
    [[ -z "$1" ]] && { cat "$cache" 2>/dev/null || command python3 ~/.local/bin/aio "$@"; return; }
    [[ "$1" == "i" ]] && { printf "Type to filter, Tab=cycle, Enter=run, Esc=quit\n\n> \033[s\n"; head -8 "$icache" 2>/dev/null | awk 'NR==1{print " > "$0}NR>1{print "   "$0}'; [[ -t 0 ]] && printf '\033[?25l' && _AIO_I=1 command python3 ~/.local/bin/aio "$@"; printf '\033[?25h'; return; }
    command python3 ~/.local/bin/aio "$@"
}
a() { aio "$@"; }
ai() { aio "$@"; }
AIOFUNC
ok "bash function"

# Node CLIs (may take a few minutes)
install_cli() {
    local pkg="$1" cmd="$2"
    if ! command -v "$cmd" &>/dev/null; then
        info "Installing $cmd..."
        if command -v npm &>/dev/null; then
            npm install -g "$pkg" && ok "$cmd" || warn "$cmd failed"
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
PIP_PKGS="pexpect prompt_toolkit keyring"; [[ "$OS" == mac ]] && PIP_FLAGS="--break-system-packages" || PIP_FLAGS=""
if command -v pip3 &>/dev/null; then pip3 install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras"
elif command -v pip &>/dev/null; then pip install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras"
elif command -v python3 &>/dev/null; then python3 -m ensurepip --user 2>/dev/null; python3 -m pip install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras" || warn "pip not available"; fi

# Enable aio tmux config if no existing tmux.conf (adds mouse support, status bar)
[[ ! -s "$HOME/.tmux.conf" ]] && "$BIN/aio" config tmux_conf y 2>/dev/null && ok "tmux config (mouse enabled)"

# Generate cache
python3 "$BIN/aio" >/dev/null 2>&1 && ok "cache generated"

# Setup sync if gh is logged in
command -v gh &>/dev/null && gh auth status &>/dev/null && python3 "$BIN/aio" backup setup 2>/dev/null && ok "sync configured"

# Final message
echo ""
echo -e "${G}══════════════════════════════════════════════════════════════${R}"
echo -e "${G}  Installation complete!${R}"
echo -e "${G}══════════════════════════════════════════════════════════════${R}"
echo ""
echo -e "${Y}⚠  IMPORTANT: To use the 'aio' command, you must either:${R}"
echo ""
echo -e "   ${C}1.${R} Open a ${G}new terminal window${R}  (recommended)"
echo ""
echo -e "   ${C}2.${R} Or run this command in your current terminal:"
echo -e "      ${C}source $RC${R}"
echo ""
echo -e "Then type ${G}aio${R} to get started!"
echo ""
