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
        sed -i -e '/^a() {/,/^}/d' -e '/^aio() {/d' -e '/^ai() {/d' "$RC" 2>/dev/null||:
        cat >> "$RC" << 'AFUNC'
a() {
    local cache=~/.local/share/a/help_cache.txt projects=~/.local/share/a/projects.txt
    # No args: print cached help (builtin read, 0ms)
    if [[ -z "$1" ]]; then
        [[ -f "$cache" ]] && printf '%s\n' "$(<"$cache")" || command a
        return
    fi
    # Number: cd to project (builtin mapfile, 0ms)
    if [[ "$1" =~ ^[0-9]+$ ]]; then
        local -a lines; mapfile -t lines < "$projects" 2>/dev/null
        local dir="${lines[$1]}"
        [[ -n "$dir" && -d "$dir" ]] && { printf '📂 %s\n' "$dir"; cd "$dir"; return; }
    fi
    # Directory: cd into it (0ms)
    local d="${1/#\~/$HOME}"; [[ "$1" == /projects/* ]] && d="$HOME$1"
    [[ -d "$d" ]] && { printf '📂 %s\n' "$d"; cd "$d"; return; }
    # .py file: time it
    [[ "$1" == *.py && -f "$1" ]] && { local s=$(($(date +%s%N)/1000000)); python3 "$@"; local r=$?; echo "{\"cmd\":\"$1\",\"ms\":$(($(($(date +%s%N)/1000000))-s)),\"ts\":\"$(date -Iseconds)\"}" >> ~/.local/share/a/timing.jsonl; return $r; }
    # Everything else: C binary
    command a "$@"
}
aio() { a "$@"; }
ai() { a "$@"; }
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
        command -v brew &>/dev/null || { info "Installing Homebrew..."; /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"; }
        brew install tmux node gh sshpass rclone 2>/dev/null || brew upgrade tmux node gh sshpass rclone 2>/dev/null; brew tap hudochenkov/sshpass 2>/dev/null
        ok "tmux + node + gh + rclone"
        ;;
    debian)
        if [[ -n "$SUDO" ]]; then
            export DEBIAN_FRONTEND=noninteractive
            $SUDO apt update -qq && $SUDO apt install -yqq tmux git curl nodejs npm python3-pip sshpass rclone gh 2>/dev/null || true
            ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo apt install tmux"; fi
        ;;
    arch)
        if [[ -n "$SUDO" ]]; then $SUDO pacman -Sy --noconfirm tmux nodejs npm git python-pip sshpass rclone github-cli 2>/dev/null && ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo pacman -S tmux"; fi
        ;;
    fedora)
        if [[ -n "$SUDO" ]]; then $SUDO dnf install -y tmux nodejs npm git python3-pip sshpass rclone gh 2>/dev/null && ok "pkgs"
        else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo dnf install tmux"; fi
        ;;
    termux) pkg update -y && pkg install -y tmux nodejs git python openssh sshpass gh rclone && ok "pkgs" ;;
    *) install_node; warn "Unknown OS - install tmux manually" ;;
esac

# Compile ac (C binary)
A_SRC="$SCRIPT_DIR/a.c"
if [[ -f "$A_SRC" ]]; then
    # Find sqlite3 headers
    SQLITE_FLAGS=""
    if [[ -d "$HOME/micromamba/include" ]]; then
        SQLITE_FLAGS="-I$HOME/micromamba/include -L$HOME/micromamba/lib -Wl,-rpath,$HOME/micromamba/lib"
    fi
    CC=clang; command -v clang &>/dev/null || CC=gcc
    $CC -O2 -Wall -Wextra -Wno-unused-parameter -Wno-unused-result \
        $SQLITE_FLAGS -o "$BIN/a" "$A_SRC" -lsqlite3 && ok "a compiled ($CC, $(wc -c < "$BIN/a") bytes)"
else
    warn "a.c not found at $A_SRC"
fi

# a-i helper
[[ -f "$SCRIPT_DIR/a-i" ]] && ln -sf "$SCRIPT_DIR/a-i" "$BIN/a-i" && chmod +x "$BIN/a-i" && ok "a-i installed"

# e editor (fast minimal editor)
E_SRC="$HOME/projects/editor/e.c"
if [[ -f "$E_SRC" ]]; then
    [[ "$OS" == termux ]] && clang -w -o "$BIN/e" "$E_SRC" || gcc -w -std=gnu89 -o "$BIN/e" "$E_SRC"
    ok "e editor (local)"
else
    E_URL="https://raw.githubusercontent.com/seanpattencode/editor/main/e.c"
    curl -fsSL "$E_URL" -o /tmp/e.c && { [[ "$OS" == termux ]] && clang -w -o "$BIN/e" /tmp/e.c || gcc -w -std=gnu89 -o "$BIN/e" /tmp/e.c; } && ok "e editor (remote)"
fi

# PATH + shell function in both shells
for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
    touch "$RC"
    grep -q '.local/bin' "$RC" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
    sed -i -e '/^a() {/,/^}/d' -e '/^aio() {/d' -e '/^ai() {/d' "$RC" 2>/dev/null||:
    cat >> "$RC" << 'AFUNC'
a() {
    local cache=~/.local/share/a/help_cache.txt projects=~/.local/share/a/projects.txt
    # No args: print cached help (builtin read, 0ms)
    if [[ -z "$1" ]]; then
        [[ -f "$cache" ]] && printf '%s\n' "$(<"$cache")" || command a
        return
    fi
    # Number: cd to project (builtin mapfile, 0ms)
    if [[ "$1" =~ ^[0-9]+$ ]]; then
        local -a lines; mapfile -t lines < "$projects" 2>/dev/null
        local dir="${lines[$1]}"
        [[ -n "$dir" && -d "$dir" ]] && { printf '📂 %s\n' "$dir"; cd "$dir"; return; }
    fi
    # Directory: cd into it (0ms)
    local d="${1/#\~/$HOME}"; [[ "$1" == /projects/* ]] && d="$HOME$1"
    [[ -d "$d" ]] && { printf '📂 %s\n' "$d"; cd "$d"; return; }
    # .py file: time it
    [[ "$1" == *.py && -f "$1" ]] && { local s=$(($(date +%s%N)/1000000)); python3 "$@"; local r=$?; echo "{\"cmd\":\"$1\",\"ms\":$(($(($(date +%s%N)/1000000))-s)),\"ts\":\"$(date -Iseconds)\"}" >> ~/.local/share/a/timing.jsonl; return $r; }
    # Everything else: C binary
    command a "$@"
}
aio() { a "$@"; }
ai() { a "$@"; }
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

# Python extras (optional, needed for fallback commands)
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

# Enable tmux config if no existing tmux.conf
[[ ! -s "$HOME/.tmux.conf" ]] && "$BIN/a" config tmux_conf y 2>/dev/null && ok "tmux config (mouse enabled)"

# Generate cache
"$BIN/a" >/dev/null 2>&1 && ok "cache generated"

# Setup sync (prompt gh login if needed)
command -v gh &>/dev/null && { gh auth status &>/dev/null || { [[ -t 0 ]] && info "GitHub login enables sync" && read -p "Login? (y/n): " yn && [[ "$yn" =~ ^[Yy] ]] && gh auth login && gh auth setup-git; }; gh auth status &>/dev/null && "$BIN/a" backup setup 2>/dev/null && ok "sync configured"; }

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
