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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"

# --shell flag: only update shell functions, skip deps
[[ "$1" == "--shell" ]] && {
    for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
        touch "$RC"
        grep -q '.local/bin' "$RC" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
        sed -i '' -e '/^a() {/,/^}/d' -e '/^aio() {/d' -e '/^ai() {/d' "$RC" 2>/dev/null||:
        cat >> "$RC" << 'AFUNC'
a() {
    local cache=~/.local/share/a/help_cache.txt projects=~/.local/share/a/projects.txt icache=~/.local/share/a/i_cache.txt
    [[ "$1" == "a" || "$1" == "ai" || "$1" == "aio" || "$1" == "all" ]] && { command python3 ~/.local/bin/a "$@"; return; }
    if [[ "$1" =~ ^[0-9]+$ ]]; then local dir=$(sed -n "$((${1}+1))p" "$projects" 2>/dev/null); [[ -d "$dir" ]] && { echo "📂 $dir"; cd "$dir"; return; }; fi
    local d="${1/#~/$HOME}"; [[ "$1" == /projects/* ]] && d="$HOME$1"; [[ -d "$d" ]] && { echo "📂 $d"; cd "$d"; ls; return; }
    [[ -z "$1" ]] && { cat "$cache" 2>/dev/null || command python3 ~/.local/bin/a "$@"; return; }
    [[ "$1" == "i" ]] && { printf "Type to filter, Tab=cycle, Enter=run, Esc=quit\n\n> \033[s\n"; awk '/^[^<=>]/{if(++n<=8)print (n==1?" > ":"   ")$0}' "$icache" 2>/dev/null; [[ -t 0 ]] && printf '\033[?25l' && _AIO_I=1 command python3 ~/.local/bin/a "$@"; printf '\033[?25h'; return; }
    [[ "$1" == *.py && -f "$1" ]] && { local s=$(($(date +%s%N)/1000000)); python3 "$@"; local r=$?; echo "{\"cmd\":\"$1\",\"ms\":$(($(($(date +%s%N)/1000000))-s)),\"ts\":\"$(date -Iseconds)\"}" >> ~/.local/share/a/timing.jsonl; return $r; }
    command python3 ~/.local/bin/a "$@"
}
aio() { echo "aio has been renamed a. Yeah i know it sucks but its faster in the long term. 2.9× fewer errors on mobile, don't need English to type a. See ideas/LATENCY.md"; a "$@"; }
AFUNC
    done
    ok "shell functions (bash + zsh)"
    exit 0
}

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
        curl -fsSL "https://nodejs.org/dist/v22.12.0/node-v22.12.0-darwin-$ARCH.tar.gz" | tar -xzf - -C "$HOME/.local" --strip-components=1
    else
        curl -fsSL "https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-$ARCH.tar.xz" | tar -xJf - -C "$HOME/.local" --strip-components=1
    fi
    command -v node &>/dev/null && ok "node $(node -v)" || warn "node install failed"
}

# Install system packages
case $OS in
    mac)
        command -v brew &>/dev/null || die "Install Homebrew first: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        brew tap hudochenkov/sshpass 2>/dev/null; brew install tmux node gh sshpass rclone 2>/dev/null || brew upgrade tmux node gh sshpass rclone 2>/dev/null || true
        ok "tmux + node + gh + rclone"
        ;;
    debian)
        if [[ -n "$SUDO" ]]; then
            export DEBIAN_FRONTEND=noninteractive
            $SUDO apt update -qq && $SUDO apt install -yqq tmux git curl nodejs npm python3-pip sshpass rclone 2>/dev/null || true
            ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo apt install tmux"; fi
        ;;
    arch)
        if [[ -n "$SUDO" ]]; then $SUDO pacman -Sy --noconfirm tmux nodejs npm git python-pip sshpass rclone 2>/dev/null && ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo pacman -S tmux"; fi
        ;;
    fedora)
        if [[ -n "$SUDO" ]]; then $SUDO dnf install -y tmux nodejs npm git python3-pip sshpass rclone 2>/dev/null && ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo dnf install tmux"; fi
        ;;
    termux) pkg update -y && pkg install -y tmux nodejs git python openssh sshpass gh rclone && ok "pkgs" ;;
    *) install_node; warn "Unknown OS - install tmux manually" ;;
esac

# aio itself
AIO_URL="https://raw.githubusercontent.com/seanpattencode/aio/main/a.py"
if [[ -f "$SCRIPT_DIR/a.py" ]]; then
    ln -sf "$SCRIPT_DIR/a.py" "$BIN/a" && chmod +x "$BIN/a" && ok "a installed (local)"
    ln -sf "$SCRIPT_DIR/a-i" "$BIN/a-i" && chmod +x "$BIN/a-i" && ok "a-i installed (local)"
else
    curl -fsSL "$AIO_URL" -o "$BIN/a" && chmod +x "$BIN/a" && ok "a installed (remote)"
    curl -fsSL "${AIO_URL%a.py}a-i" -o "$BIN/a-i" && chmod +x "$BIN/a-i" && ok "a-i installed (remote)"
fi

# PATH + aio function in both shells
for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
    touch "$RC"
    grep -q '.local/bin' "$RC" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
    sed -i '' -e '/^a() {/,/^}/d' -e '/^aio() {/d' -e '/^ai() {/d' "$RC" 2>/dev/null||:
    cat >> "$RC" << 'AFUNC'
a() {
    local cache=~/.local/share/a/help_cache.txt projects=~/.local/share/a/projects.txt icache=~/.local/share/a/i_cache.txt
    [[ "$1" == "a" || "$1" == "ai" || "$1" == "aio" || "$1" == "all" ]] && { command python3 ~/.local/bin/a "$@"; return; }
    if [[ "$1" =~ ^[0-9]+$ ]]; then local dir=$(sed -n "$((${1}+1))p" "$projects" 2>/dev/null); [[ -d "$dir" ]] && { echo "📂 $dir"; cd "$dir"; return; }; fi
    local d="${1/#~/$HOME}"; [[ "$1" == /projects/* ]] && d="$HOME$1"; [[ -d "$d" ]] && { echo "📂 $d"; cd "$d"; ls; return; }
    [[ -z "$1" ]] && { cat "$cache" 2>/dev/null || command python3 ~/.local/bin/a "$@"; return; }
    [[ "$1" == "i" ]] && { printf "Type to filter, Tab=cycle, Enter=run, Esc=quit\n\n> \033[s\n"; awk '/^[^<=>]/{if(++n<=8)print (n==1?" > ":"   ")$0}' "$icache" 2>/dev/null; [[ -t 0 ]] && printf '\033[?25l' && _AIO_I=1 command python3 ~/.local/bin/a "$@"; printf '\033[?25h'; return; }
    [[ "$1" == *.py && -f "$1" ]] && { local s=$(($(date +%s%N)/1000000)); python3 "$@"; local r=$?; echo "{\"cmd\":\"$1\",\"ms\":$(($(($(date +%s%N)/1000000))-s)),\"ts\":\"$(date -Iseconds)\"}" >> ~/.local/share/a/timing.jsonl; return $r; }
    command python3 ~/.local/bin/a "$@"
}
aio() { echo "aio has been renamed a. Yeah i know it sucks but its faster in the long term. 2.9× fewer errors on mobile, don't need English to type a. See ideas/LATENCY.md"; a "$@"; }
AFUNC
done
ok "shell functions (bash + zsh)"

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
PIP_PKGS="pexpect prompt_toolkit"; [[ "$OS" == mac ]] && PIP_FLAGS="--break-system-packages" || PIP_FLAGS=""
if command -v pip3 &>/dev/null; then pip3 install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras"
elif command -v pip &>/dev/null; then pip install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras"
elif command -v python3 &>/dev/null; then python3 -m ensurepip --user 2>/dev/null; python3 -m pip install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras" || warn "pip not available"; fi

# Ollama (local LLMs)
if ! command -v ollama &>/dev/null; then
    if [[ -n "$SUDO" ]] || [[ $EUID -eq 0 ]]; then
        info "Installing ollama..."
        curl -fsSL https://ollama.com/install.sh | sh && ok "ollama" || warn "ollama install failed"
    else warn "ollama needs sudo - run: curl -fsSL https://ollama.com/install.sh | sudo sh"; fi
else ok "ollama (exists)"; fi

# Enable aio tmux config if no existing tmux.conf (adds mouse support, status bar)
[[ ! -s "$HOME/.tmux.conf" ]] && "$BIN/a" config tmux_conf y 2>/dev/null && ok "tmux config (mouse enabled)"

# Generate cache
python3 "$BIN/a" >/dev/null 2>&1 && ok "cache generated"

# Setup sync (prompt gh login if needed)
command -v gh &>/dev/null && { gh auth status &>/dev/null || { [[ -t 0 ]] && info "GitHub login enables sync" && read -p "Login? (y/n): " yn && [[ "$yn" =~ ^[Yy] ]] && gh auth login && gh auth setup-git; }; gh auth status &>/dev/null && python3 "$BIN/a" backup setup 2>/dev/null && ok "sync configured"; }

# Final message
echo ""
echo -e "${G}══════════════════════════════════════════════════════════════${R}"
echo -e "${G}  Installation complete!${R}"
echo -e "${G}══════════════════════════════════════════════════════════════${R}"
echo ""
echo -e "${Y}⚠  IMPORTANT: To use the 'a' command, you must either:${R}"
echo ""
echo -e "   ${C}1.${R} Open a ${G}new terminal window${R}  (recommended)"
echo ""
echo -e "   ${C}2.${R} Or source your shell rc:"
echo -e "      ${C}source ~/.bashrc${R}  or  ${C}source ~/.zshrc${R}"
echo ""
echo -e "Then type ${G}a${R} to get started!"
echo ""
