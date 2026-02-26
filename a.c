#if 0
# ── a.c — self-compiling C program ──
#
# sh a.c              build (two-pass parallel: checker + builder)
# sh a.c install      full install (deps, compile, shell, CLIs)
# sh a.c analyze      static analyzer
# sh a.c shell        refresh shell functions
# sh a.c clean        remove binary
#
# The #if 0 block is a polyglot: shell sees # as comments and runs the
# script; the C preprocessor skips everything between #if 0 and #endif.
# Three files (a.c + Makefile + install.sh) become one.
#
# TERMUX + CLAUDE CODE:
# Sandbox monitors "bash <script>", tries mkdir /tmp which Termux denies
# (owned by shell:shell 0771). Direct commands skip sandbox path and work.
# Also set CLAUDE_CODE_TMPDIR=$HOME/.tmp (see _shell_funcs below).
# Manual build (bypass sandbox): run compiler directly, not "bash a.c".
#   D=/data/data/com.termux/files/home/projects/a
#   clang-21 -DSRC="\"$D\"" -isystem "$HOME/micromamba/include" \
#     -O3 -march=native -flto -w -o "$D/a" "$D/a.c"

[ -z "$BASH_VERSION" ] && exec bash "$0" "$@"
set -e
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

G='\033[32m' Y='\033[33m' C='\033[36m' R='\033[0m'
ok() { echo -e "${G}✓${R} $1"; }
info() { echo -e "${C}>${R} $1"; }
warn() { echo -e "${Y}!${R} $1"; }

_ensure_cc() {
    CC=$(compgen -c clang- 2>/dev/null|grep -xE 'clang-[0-9]+'|sort -t- -k2 -rn|head -1) || CC=""
    [[ -z "$CC" ]] && for CC in clang gcc; do command -v $CC &>/dev/null && break; done
    [[ -n "$CC" ]] && return 0
    # Auto-install clang (prefer LLVM apt repo for latest on debian)
    info "No C compiler found — installing clang..."
    if [[ -f /data/data/com.termux/files/usr/bin/bash ]]; then
        pkg install -y clang
    elif [[ -f /etc/debian_version ]]; then
        T=/tmp/llvm.sh && curl -fsSL https://apt.llvm.org/llvm.sh -o $T && sudo bash $T $(grep -o 'PATTERNS\[[0-9]*' $T|grep -o '[0-9]*'|sort -rn|head -1) 2>/dev/null || sudo apt-get install -y clang
    elif [[ -f /etc/arch-release ]]; then
        sudo pacman -S --noconfirm clang
    elif [[ -f /etc/fedora-release ]]; then
        sudo dnf install -y clang
    elif [[ "$OSTYPE" == darwin* ]]; then
        xcode-select --install 2>/dev/null; echo "Run 'xcode-select --install' and retry"; exit 1
    else
        echo "ERROR: No C compiler (clang/gcc). Install one and retry."; exit 1
    fi
    command -v clang &>/dev/null && { CC=clang; return 0; }
    echo "ERROR: clang install failed."; exit 1
}

_warn_flags() {
    WARN="-std=c17 -Werror -Weverything"
    WARN+=" -Wno-padded -Wno-disabled-macro-expansion -Wno-reserved-id-macro"
    WARN+=" -Wno-documentation -Wno-declaration-after-statement"
    WARN+=" -Wno-unsafe-buffer-usage -Wno-used-but-marked-unused"
    WARN+=" -Wno-pre-c11-compat" # glibc expands _Generic at call site; not actionable, already c17
    WARN+=" --system-header-prefix=/usr/include -isystem /usr/local/include"
    $CC -Werror -Wno-implicit-void-ptr-cast -x c -c /dev/null -o /dev/null 2>/dev/null && WARN+=" -Wno-implicit-void-ptr-cast" || :
    $CC -Werror -Wno-nullable-to-nonnull-conversion -x c -c /dev/null -o /dev/null 2>/dev/null && WARN+=" -Wno-nullable-to-nonnull-conversion" || :
    $CC -Werror -Wno-poison-system-directories -x c -c /dev/null -o /dev/null 2>/dev/null && WARN+=" -Wno-poison-system-directories" || :
    HARDEN="-fstack-protector-strong -ftrivial-auto-var-init=zero -fno-common -D_FORTIFY_SOURCE=3 -fvisibility=hidden"
    # these flags + stack-clash/cf-protection unsupported on darwin; || : for bash 3.2 set -e
    [[ "$(uname)" != "Darwin" ]] && HARDEN+=" -fsanitize=safe-stack -fsanitize=cfi -fstack-clash-protection -fcf-protection=full" || :
}

_shell_funcs() {
    for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
        touch "$RC"
        grep -q '.local/bin' "$RC" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
        sed -i -e '/^_ADD=/d' -e '/^a() {/,/^}/d' -e '/^aio() {/,/^}/d' -e '/^ai() {/,/^}/d' "$RC" 2>/dev/null||:
        echo "_ADD=\"${D%%/adata/worktrees/*}/adata/local\"" >> "$RC"
        cat >> "$RC" << 'AFUNC'
a() {
    local dd="$_ADD"
    [[ -z "$1" ]] && { [[ -t 1 ]] && set -- i || { [[ -f $dd/help_cache.txt ]] && printf '%s\n' "$(<"$dd/help_cache.txt")" || command a; return; }; }
    local d="${1/#\~/$HOME}"; [[ "$1" == "/projects/"* ]] && d="$HOME$1"
    [[ -d "$d" ]] && { printf '📂 %s\n' "$d"; cd "$d"; return; }
    [[ "$1" == *.py && -f "$1" ]] && { local py=python3 ev=1; [[ -n "$VIRTUAL_ENV" ]] && py="$VIRTUAL_ENV/bin/python" ev=0; [[ -x .venv/bin/python ]] && py=.venv/bin/python ev=0; local s=$(($(date +%s%N)/1000000)); if command -v uv &>/dev/null && [[ -f pyproject.toml || -f uv.lock ]]; then uv run python "$@"; ev=0; else $py "$@"; fi; local r=$?; echo "{\"cmd\":\"$1\",\"ms\":$(($(($(date +%s%N)/1000000))-s)),\"ts\":\"$(date -Iseconds)\"}" >> $dd/timing.jsonl; [[ $r -ne 0 && $ev -ne 0 ]] && printf '  try: a c fix python env for this project\n'; return $r; }
    [[ "$1" == copy && -z "$TMUX" && -t 0 ]] && { local lc=$(fc -ln -2 -2 2>/dev/null|sed 's/^ *//'); [[ "$lc" && "$lc" != a\ copy* ]] && { eval "$lc" 2>&1|command a copy; return; }; echo "x No prev cmd"; return 1; }
    command a "$@"; [[ -f $dd/cd_target ]] && { read -r d < $dd/cd_target; rm $dd/cd_target; cd "$d" 2>/dev/null; }
}
aio() { a "$@"; }
ai() { a "$@"; }
AFUNC
    done
    # Termux: /tmp not writable, redirect Claude Code tmpdir
    if [[ -d /data/data/com.termux ]]; then
        mkdir -p "$HOME/.tmp"
        grep -q CLAUDE_CODE_TMPDIR "$HOME/.bashrc" 2>/dev/null || echo 'export CLAUDE_CODE_TMPDIR="$HOME/.tmp"' >> "$HOME/.bashrc"
        tmux set-environment -g CLAUDE_CODE_TMPDIR "$HOME/.tmp" 2>/dev/null || :
    fi
    ok "shell functions (bash + zsh)"
}

case "${1:-build}" in
build)
    # LLMs: always "sh a.c && command a <args>" to test (see comment below)
    _ensure_cc
    _warn_flags
    R="${D%%/adata/worktrees/*}"
    $CC $WARN $HARDEN -DSRC="\"$D\"" -O3 -flto -fsyntax-only "$D/a.c" & P1=$!
    $CC -DSRC="\"$D\"" -isystem "$HOME/micromamba/include" -O3 -march=native -flto -w -o "$R/a" "$D/a.c" $LDFLAGS & P2=$!
    $CC -O2 -march=native -w -o "$R/a-i" "$D/lib/aid.c" & P3=$!
    wait $P1 && wait $P2 && wait $P3
    BIN="$HOME/.local/bin"; mkdir -p "$BIN"; ln -sf "$R/a" "$BIN/a"; [ -f "$R/a-i" ] && ln -sf "$R/a-i" "$BIN/a-i"
    "$R/a-i" --stop 2>/dev/null || :
    ;;
analyze)
    _ensure_cc
    _warn_flags
    $CC $WARN -DSRC="\"$D\"" --analyze \
        -Xanalyzer -analyzer-checker=security,unix,nullability,optin.portability.UnixAPI \
        -Xanalyzer -analyzer-disable-checker=security.insecureAPI.DeprecatedOrUnsafeBufferHandling "$D/a.c"
    ;;
shell)
    _shell_funcs
    ;;
clean)
    rm -f "$D/a"
    ;;
install)
    BIN="$HOME/.local/bin"; mkdir -p "$BIN"; export PATH="$BIN:$PATH"
    if [[ "$OSTYPE" == darwin* ]]; then OS=mac
    elif [[ -f /data/data/com.termux/files/usr/bin/bash ]]; then OS=termux
    elif [[ -f /etc/debian_version ]]; then OS=debian
    elif [[ -f /etc/arch-release ]]; then OS=arch
    elif [[ -f /etc/fedora-release ]]; then OS=fedora
    else OS=unknown; fi
    SUDO="" NEED_SUDO=0
    ! command -v tmux &>/dev/null || ! command -v npm &>/dev/null && NEED_SUDO=1
    ! grep -q 'a\.local' /etc/hosts 2>/dev/null && NEED_SUDO=1
    if [[ $EUID -eq 0 ]]; then SUDO=""
    elif sudo -n true 2>/dev/null; then SUDO="sudo"
    elif [[ $NEED_SUDO -eq 1 ]] && command -v sudo &>/dev/null && [[ -t 0 ]]; then info "sudo needed for system packages + /etc/hosts"; sudo -v && SUDO="sudo"
    fi
    info "Detected: $OS ${SUDO:+(sudo)}${SUDO:-"(no root)"}"
    # a.local hostname — do this first while sudo cache is fresh
    if ! grep -q 'a\.local' /etc/hosts 2>/dev/null; then
        if [[ -n "$SUDO" ]] || [[ $EUID -eq 0 ]]; then
            echo '127.0.0.1 a.local' | $SUDO tee -a /etc/hosts >/dev/null && ok "a.local (added to /etc/hosts)"
        elif [[ "$OS" == termux ]]; then ok "a.local (termux: use localhost:1111)"
        else warn "a.local: run 'echo 127.0.0.1 a.local | sudo tee -a /etc/hosts'"; fi
    else ok "a.local (exists)"; fi
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
    case $OS in
        mac)
            command -v brew &>/dev/null || { info "Installing Homebrew..."; /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"; }
            brew install tmux node gh sshpass rclone 2>/dev/null || brew upgrade tmux node gh sshpass rclone 2>/dev/null; brew tap hudochenkov/sshpass 2>/dev/null
            command -v clang &>/dev/null || { xcode-select --install 2>/dev/null; warn "Run 'xcode-select --install' then retry"; }
            ok "tmux + node + gh + rclone" ;;
        debian)
            if [[ -n "$SUDO" ]]; then export DEBIAN_FRONTEND=noninteractive
                $SUDO apt update -qq && $SUDO apt install -yqq clang tmux git curl nodejs npm python3-pip sshpass rclone gh 2>/dev/null || true; ok "pkgs"
            else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo apt install tmux"; fi ;;
        arch)
            if [[ -n "$SUDO" ]]; then $SUDO pacman -Sy --noconfirm clang tmux nodejs npm git python-pip sshpass rclone github-cli 2>/dev/null && ok "pkgs"
            else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo pacman -S tmux"; fi ;;
        fedora)
            if [[ -n "$SUDO" ]]; then $SUDO dnf install -y clang tmux nodejs npm git python3-pip sshpass rclone gh 2>/dev/null && ok "pkgs"
            else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo dnf install tmux"; fi ;;
        termux) pkg update -y && pkg upgrade -y -o Dpkg::Options::=--force-confold && pkg install -y clang tmux nodejs git python openssh sshpass gh rclone cronie termux-services && ok "pkgs" ;;
        *) install_node; warn "Unknown OS - install tmux manually" ;;
    esac
    _ensure_cc
    sh "$D/a.c" && ok "a compiled ($CC, $(wc -c < "$D/a") bytes)" || warn "Build failed"
    ln -sf "$D/a" "$BIN/a"
    [[ -f "$D/a-i" ]] && ln -sf "$D/a-i" "$BIN/a-i" && chmod +x "$BIN/a-i" && ok "a-i installed" || :
    E="$HOME/projects/editor"
    [[ -f "$E/e.c" ]] || git clone https://github.com/seanpattencode/editor "$E" 2>/dev/null || :
    [[ -f "$E/e.c" ]] && sh "$E/e.c" install || :
    _shell_funcs
    install_cli() {
        local pkg="$1" cmd="$2"
        if ! command -v "$cmd" &>/dev/null; then
            info "Installing $cmd..."
            if command -v npm &>/dev/null; then npm install -g "$pkg" && ok "$cmd" || warn "$cmd failed"
            else warn "$cmd skipped (npm not found)"; fi
        else ok "$cmd (exists)"; fi
    }
    if ! command -v claude &>/dev/null; then
        info "Installing claude..."
        curl -fsSL https://claude.ai/install.sh | bash && ok "claude" || warn "claude install failed"
    else ok "claude (exists)"; fi
    install_cli "@openai/codex" "codex"
    install_cli "@google/gemini-cli" "gemini"
    # uv — preferred python env. auto-installs deps from PEP 723 metadata.
    # fallback_py() tries uv run --script first, then venv, then system python3.
    if ! command -v uv &>/dev/null; then
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH="$HOME/.local/bin:$PATH" && ok "uv" || warn "uv install failed"
    else ok "uv ($(uv --version))"; fi
    # venv fallback — for systems where uv is unavailable
    _best_py() {
        for v in python3.14 python3.13 python3.12 python3.11 python3; do command -v $v &>/dev/null && { $v -c 'import venv' 2>/dev/null && echo $v && return; }; done
    }
    VENV="$D/adata/venv"; PY=$(_best_py)
    if ! command -v uv &>/dev/null && [[ -n "$PY" ]]; then
        if [[ ! -f "$VENV/bin/python" ]]; then
            info "Creating venv with $PY..."
            $PY -m venv "$VENV" && ok "venv ($($VENV/bin/python --version))" || warn "venv creation failed"
        else ok "venv (exists: $($VENV/bin/python --version))"; fi
        [[ -f "$VENV/bin/pip" ]] && $VENV/bin/pip install -q pexpect prompt_toolkit aiohttp 2>/dev/null && ok "python deps" || warn "pip install failed"
    fi
    # playwright browser deps (needed for headless scraping agents)
    if ! python3 -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.chromium.launch(headless=True).close(); p.stop()" 2>/dev/null; then
        if command -v pacman &>/dev/null; then
            info "Installing playwright browser deps..."
            sudo pacman -S --noconfirm --needed libxcomposite gtk3 alsa-lib nss 2>/dev/null && ok "playwright deps" || warn "playwright deps (needs sudo)"
        elif command -v apt-get &>/dev/null; then
            info "Installing playwright browser deps..."
            sudo apt-get install -y libxcomposite1 libgtk-3-0t64 libasound2t64 libnss3 2>/dev/null && ok "playwright deps" || warn "playwright deps (needs sudo)"
        fi
    else ok "playwright deps"; fi
    if ! command -v ollama &>/dev/null; then
        if [[ -n "$SUDO" ]] || [[ $EUID -eq 0 ]]; then
            info "Installing ollama..."
            curl -fsSL https://ollama.com/install.sh | sh && ok "ollama" || warn "ollama install failed"
        else warn "ollama needs sudo - run: curl -fsSL https://ollama.com/install.sh | sudo sh"; fi
    else ok "ollama (exists)"; fi
    "$BIN/a" ui on 2>/dev/null && ok "UI service (localhost:1111)" || :
    [[ ! -s "$HOME/.tmux.conf" ]] && "$BIN/a" config tmux_conf y 2>/dev/null && ok "tmux config (mouse enabled)" || :
    "$BIN/a" >/dev/null 2>&1 && ok "cache generated" || :
    command -v gh &>/dev/null && { gh auth status &>/dev/null || { [[ -t 0 ]] && info "GitHub login enables sync" && read -p "Login? (y/n): " yn && [[ "$yn" =~ ^[Yy] ]] && gh auth login && gh auth setup-git; }; gh auth status &>/dev/null && ok "sync configured"; } || :
    # Ensure adata/git exists (after gh auth so clone can work)
    AROOT="$D/adata"; SROOT="$AROOT/git"
    if [[ ! -d "$SROOT/.git" ]]; then
        mkdir -p "$AROOT"
        if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
            gh repo clone seanpattencode/a-git "$SROOT" 2>/dev/null && ok "adata/git cloned" || { git init -q "$SROOT" 2>/dev/null; ok "adata/git initialized (no remote)"; }
        else
            git init -q "$SROOT" 2>/dev/null; ok "adata/git initialized (gh auth login to enable sync)"
        fi
    fi
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
    ;;
*)
    echo "Usage: sh a.c [build|install|analyze|shell|clean]"
    ;;
esac
exit 0
#endif
/*
 * a.c - AI agent session manager (self-compiling)
 *
 * Amalgamation: a.c is the program — includes, constants, and dispatch.
 * The compiler follows #include "lib/foo.c" to build one translation unit.
 * No header file, no build system. Ordering = dependency resolution.
 *
 * Build:    sh a.c             two clang passes in parallel (check + build)
 * Install:  bash a.c install   deps, compile, shell functions, CLIs
 * Analyze:  sh a.c analyze     static analysis
 *
 * Terminal is the API: all logic runs as terminal commands. The UI (a ui)
 * is a pure visualizer — no business logic, just renders what the terminal
 * computes. This keeps functionality identical for terminal users, UI users,
 * AI agents, and humans. One interface, many surfaces.
 *
 * IMPORTANT — AI agent testing:
 *   Always test with "command a <args>", never "./a <args>". The binary
 *   runs through ~/.local/bin/a (a symlink), which is how real users invoke
 *   it. "./a" bypasses the symlink and hides bugs in path resolution,
 *   install state, and init_paths. Always run "sh a.c" first to rebuild +
 *   re-symlink, then "command a <args>" to test the installed binary.
 *   Example: a bug where "a 0" failed with "Invalid index" was invisible
 *   via ./a (exe in project dir, paths resolve fine) but reproduced via
 *   command a (symlink pointed to a worktree binary, AROOT was wrong).
 *   "sh a.c" also runs the strict -Weverything checker in parallel with the
 *   build. Skipping it (./a, or manual gcc) means code that compiles fine
 *   now but fails the checker on the next real build. Strict checks catch
 *   real bugs (implicit conversions, sign issues, unused results) that
 *   compound over time — the checker is the gatekeeper, not optional.
 *   The pattern: sh a.c && command a 0   — build like install, test like user.
 *
 * Add a command:  write lib/foo.c, add #include + dispatch line here.
 * Remove:         delete the file, delete two lines.
 *
 * Agent-to-agent control (agents can launch and delegate to other agents):
 *   Launch:  a g                                 start gemini in current dir
 *            a c / a co / a g                    claude / codex / gemini
 *            a c 3 "fix the bug"                 claude in project #3 with prompt
 *   Send:    a send <session> <prompt> --wait    send + wait for idle
 *            a watch <session> [duration]         read pane output
 *   Remote:  a ssh <host> a send <session> ...   cross-device delegation
 *   ADB:     a adb ssh                           start sshd on USB Termux devices
 *   Tmux:    tmux send-keys / capture-pane       raw escape hatch for fine control
 *   Always use a commands, not raw tmux. "a g" launches gemini with --yolo
 *   (auto-approve), env fixes, named session — vs raw tmux which needs manual
 *   permission clicks, env setup, session naming. Shorter commands (~10 vs ~30
 *   tokens) means faster LLM generation, fewer errors, and less chance of an
 *   agent using the wrong flags. Brevity compounds across thousands of calls.
 *   An agent can spin up another agent (even a different model) to handle a
 *   subtask — same interface humans use, no special API.
 *
 * References:
 *   Dispatch — sorted table + bsearch, inspired by Linux syscall_64.c
 *     (integer→function via switch/jump table). Our analog: sorted string→
 *     function table, O(log n). ~90 aliases, ~50 commands.
 *     https://github.com/torvalds/linux/blob/master/arch/x86/entry/syscall_64.c
 *   Amalgamation — SQLite mksqlite3c.tcl: concatenates 100+ .c/.h into one
 *     sqlite3.c translation unit. Same idea, we just use #include directly.
 *     https://sqlite.org/src/file?ci=tip&name=tool/mksqlite3c.tcl
 */
#ifndef __APPLE__
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <dirent.h>
#include <time.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <ctype.h>
#include <limits.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

/*
 * ═══ DATA LAYOUT ═══
 *
 * Principle: all persistence lives in adata/. If it's not in adata, nobody
 * knows where it is. Maximum visibility for humans and LLMs — one place to
 * look, one place to back up. VS Code opens a/ and sees everything.
 *
 * adata/ lives inside the project dir but is .gitignored — the parent a/
 * repo is completely blind to it. adata/git/ is its own independent git
 * repo (NOT a submodule) with its own remote. Two repos, one directory tree.
 *
 * a/adata/                    AROOT — all data (.gitignored by parent)
 *   local/                    DDIR — per-device state (not synced)
 *     config.txt                key:value settings (prompts, worktrees_dir)
 *     sessions.txt              session defs (key|name|cmd)
 *     projects.txt              one path per line, index = project number
 *     .device                   device identity (hostname on first run)
 *     help_cache.txt            cached help + project list
 *     i_cache.txt               interactive picker cache
 *     cd_target                 temp file for shell cd
 *     agent_logs.txt            session start log (name, timestamp, device)
 *     timing.jsonl              command timing (from shell function)
 *     logs/push.ok              instant push flag (valid 10 min)
 *   git/                      SROOT — git push/pull, all devices (only git repo)
 *     activity/                 command log (one .txt per invocation)
 *     notes/                    quick notes (.txt, key:value)
 *     tasks/                    task dirs (priority-slug/, prompts, sessions)
 *     workspace/projects/       project registry (.txt per project)
 *     workspace/cmds/           custom commands (.txt per command)
 *     ssh/                      host registry (.txt per host)
 *     common/prompts/           shared prompt templates
 *     jobs/                     saved prompts (.txt) + tmux visual logs (.log)
 *     context/                  agent context files (.txt, togglable)
 *     docs/                     user documents
 *   venv/                     Python venv fallback (if uv unavailable).
 *                               fallback_py() tries: uv run --script (preferred,
 *                               auto-installs deps via PEP 723), venv/bin/python,
 *                               then system python3.
 *   sync/                     rclone copy <->, all devices, large files <5G
 *   vault/                    rclone copy on-demand, big devices, models
 *   backup/                   rclone move ->, all devices, logs+state
 *     {device}/               LOGDIR — session logs ({device}__{session}.log)
 *                             + claude JSONL transcripts (full conversation, 1-13MB)
 *                             (tmux visual logs are small, in git/jobs/ instead)
 * ~/.local/bin/a              symlink to compiled binary
 */

#define P 1024
#define B 4096
#define MP 256
#define MA 64
#define MS 48

static void alog(const char *cmd, const char *cwd, const char *extra);
static void perf_disarm(void);

/* ═══ AMALGAMATION ═══ */
#include "lib/globals.c"  /* state: paths, projects, sessions */
#include "lib/init.c"     /* resolve paths + device id */
#include "lib/util.c"     /* file/string/exec helpers */
#include "lib/kv.c"       /* key:value parser + listdir */
#include "lib/data.c"     /* config, projects, sessions db */
#include "lib/tmux.c"     /* tmux has/go/new/send */
#include "lib/git.c"      /* git helpers + adata sync */
#include "lib/session.c"  /* create session + auto-prompt */
#include "lib/alog.c"     /* activity log (async write) */
#include "lib/help.c"     /* help, list, cache, misc cmds */
#include "lib/project.c"  /* cd-to-project + add/remove/scan */
#include "lib/config.c"   /* set, config, prompt, install */
#include "lib/push.c"     /* push, pull, diff, revert */
#include "lib/ls.c"       /* ls, kill, copy, send, jobs */
#include "lib/note.c"     /* notes + tasks (priority/review) */
#include "lib/ssh.c"      /* ssh connect/add/broadcast */
#include "lib/hub.c"      /* hub: scheduled jobs */
#include "lib/net.c"      /* sync, update, log, login */
#include "lib/agent.c"    /* autonomous agent + multi-run */
#include "lib/perf.c"     /* benchmark + timing display */
#include "lib/sess.c"     /* session dispatch (c/g/co/etc) */

/* ═══ PY-ONLY WRAPPERS — C entry points for commands still in Python ═══ */
static int cmd_cat(int c,char**v){if(c>2&&chdir(v[2]))return 1;perf_disarm();
    const char*cc=clip_cmd();if(!cc){puts("x Needs tmux");return 1;}
    char cm[B];snprintf(cm,B,"git ls-files -z|xargs -0 grep -lIZ ''|xargs -0 tail -n+1|%s&&echo >&2 '✓ copied'",cc);
    return system(cm);}
static int cmd_gdrive(int argc, char **argv) { fallback_py("gdrive", argc, argv); }
static int cmd_ask(int argc, char **argv)    { fallback_py("ask", argc, argv); }
static int cmd_ui(int argc, char **argv)     { fallback_py("ui/__init__", argc, argv); }
static int cmd_job(int c,char**v){
    if(c<3||(*v[2]>='0'&&*v[2]<='9')||!strcmp(v[2],"rm")||!strcmp(v[2],"watch")||!strcmp(v[2],"-r"))return cmd_jobs(c,v);
    fallback_py("job",c,v);}
static int cmd_mono(int argc, char **argv)   { fallback_py("mono", argc, argv); }
static int cmd_work(int argc, char **argv)   { fallback_py("work", argc, argv); }
static int cmd_j(int c,char**v){
    if(c<3||!strcmp(v[2],"rm")||!strcmp(v[2],"watch")||!strcmp(v[2],"-r"))return cmd_jobs(c,v);
    if(c==3&&v[2][0]>='0'&&v[2][0]<='9')return cmd_jobs(c,v);
    /* limit concurrent jobs: each claude ~1.2GB RSS */
    {char nb[16]="";pcmd("pgrep -xc claude 2>/dev/null||echo 0",nb,16);
    int nj=atoi(nb)-1;if(nj<0)nj=0; /* -1 for this session */
    if(nj>=4&&!(c>2&&!strcmp(v[2],"--resume"))){printf("x %d/4 job slots full — use 'a job' to see running\n",nj);return 1;}}
    init_db();load_cfg();load_proj();char wd[P];if(!getcwd(wd,P))snprintf(wd,P,"%s",HOME);
    /* resume: a j --resume <worktree-path> */
    if(c>3&&!strcmp(v[2],"--resume")){snprintf(wd,P,"%s",v[3]);
        char jf[P],*jp;snprintf(jf,P,"%s/.a_job",wd);jp=readf(jf,NULL);
        if(!jp){printf("x No .a_job in %s\n",wd);return 1;}
        printf("+ resume: %s\n",wd);
        /* no ulimit: bun/nucleo need unbounded virt-mem; 4-slot limit is the real guard */
        tm_ensure_conf();char jcmd[B];snprintf(jcmd,B,"while :;do claude --dangerously-skip-permissions --continue;e=$?;[ $e -eq 0 ]&&break;echo \"$(date) $e $(pwd)\">>%s/crashes.log;echo \"! crash $e, restarting..\";sleep 2;done",LOGDIR);
        if(!getenv("TMUX")){char sn[64];snprintf(sn,64,"j-%s",bname(wd));tm_new(sn,wd,jcmd);tm_go(sn);}
        else{char cm[B],pid[64];snprintf(cm,B,"tmux new-window -P -F '#{pane_id}' -c '%s' '%s'",wd,jcmd);pcmd(cm,pid,64);}
        free(jp);return 0;}
    int si=2,nowt=0;if(c>3&&v[2][0]>='0'&&v[2][0]<='9'){int idx=atoi(v[2]);if(idx<NPJ)snprintf(wd,P,"%s",PJ[idx].path);si++;}
    char pr[B]="";int pl=0;for(int i=si;i<c;i++){if(!strcmp(v[i],"--no-wt")){nowt=1;continue;}pl+=snprintf(pr+pl,(size_t)(B-pl),"%s%s",pl?" ":"",v[i]);}
    /* worktree */
    if(!nowt&&git_in_repo(wd)){
        const char*w=cfget("worktrees_dir");char wt[P];
        if(w[0])snprintf(wt,P,"%s",w);else snprintf(wt,P,"%s/worktrees",AROOT);
        time_t now=time(NULL);struct tm*t=localtime(&now);char ts[16];
        strftime(ts,16,"%b%d",t);for(char*p=ts;*p;p++)*p=(*p>='A'&&*p<='Z')?*p+32:*p;
        int h=t->tm_hour%12;if(!h)h=12;char nm[64],wp[P],gc[B];
        snprintf(nm,64,"%s-%s-%d%02d%02d%s",bname(wd),ts,h,t->tm_min,t->tm_sec,t->tm_hour>=12?"pm":"am");
        snprintf(wp,P,"%s/%s",wt,nm);
        snprintf(gc,B,"mkdir -p '%s'&&git -C '%s' worktree add -b 'j-%s' '%s' HEAD 2>/dev/null",wt,wd,nm,wp);
        if(!system(gc)){printf("+ %s\n",wp);snprintf(wd,P,"%s",wp);}
    }
    {char jf[P];snprintf(jf,P,"%s/.a_job",wd);FILE*f=fopen(jf,"w");if(f){fprintf(f,"%s",pr);fclose(f);}}
    printf("+ job: %s\n  %.*s\n",bname(wd),80,pr);
    if(pr[0])pl+=snprintf(pr+pl,(size_t)(B-pl),"\n\nWhen done, run: a done \"<summary>\"");
    tm_ensure_conf();
    char jcmd[B];snprintf(jcmd,B,"while :;do claude --dangerously-skip-permissions;e=$?;[ $e -eq 0 ]&&break;echo \"$(date) $e $(pwd)\">>%s/crashes.log;echo \"! crash $e, restarting..\";sleep 2;done",LOGDIR);
    if(!getenv("TMUX")){char sn[64];snprintf(sn,64,"j-%s",bname(wd));
        tm_ensure_conf();tm_new(sn,wd,jcmd);send_prefix_bg(sn,"claude",wd,pr);tm_go(sn);}
    char cm[B],pid[64];
    snprintf(cm,B,"tmux new-window -P -F '#{pane_id}' -c '%s' '%s'",wd,jcmd);
    pcmd(cm,pid,64);pid[strcspn(pid,"\n")]=0;if(pid[0])send_prefix_bg(pid,"claude",wd,pr);
    return 0;}
static int cmd_adb(int c,char**v){
    if(c>2&&!strcmp(v[2],"ssh"))return system("for s in $(adb devices|awk '/\\tdevice$/{print$1}');do printf '\\033[36m→ %s\\033[0m ' \"$s\";adb -s \"$s\" shell 'am broadcast -n com.termux/.app.TermuxOpenReceiver -a com.termux.RUN_COMMAND --es com.termux.RUN_COMMAND_PATH /data/data/com.termux/files/usr/bin/sshd --ez com.termux.RUN_COMMAND_BACKGROUND true' 2>&1|tail -1;done");
    (void)c;(void)v;execlp("adb","adb","devices","-l",(char*)0);return 1;
}

/* ── once — headless single-shot claude -p (opus, 10min default) ── */
static int cmd_run_once(int c,char**v){
    if(c<3){puts("Usage: a once [-t secs] [claude flags] prompt words...");return 1;}
    unsigned tl=600;int si=2;
    if(c>3&&!strcmp(v[2],"-t")){tl=(unsigned)atoi(v[3]);si=4;}
    perf_disarm();unsetenv("CLAUDECODE");unsetenv("CLAUDE_CODE_ENTRYPOINT");
    char*flags[16];int nf=0;char pr[B]="";int pl=0;
    for(int i=si;i<c;i++){
        if(v[i][0]=='-'&&nf<14){flags[nf++]=v[i];
            if((!strcmp(v[i],"--model")||!strcmp(v[i],"--max-budget-usd"))&&i+1<c)flags[nf++]=v[++i];
        }else pl+=snprintf(pr+pl,(size_t)(B-pl),"%s%s",pl?" ":"",v[i]);}
    char**a=malloc(((unsigned)nf+7)*sizeof(char*));int n=0;
    a[n++]="claude";a[n++]="-p";a[n++]="--dangerously-skip-permissions";a[n++]="--model";a[n++]="opus";
    for(int i=0;i<nf;i++)a[n++]=flags[i];
    a[n++]=pr;a[n]=NULL;
    pid_t ch=fork();
    if(ch==0){execvp("claude",a);perror("claude");_exit(127);}
    free(a);int st;
    for(unsigned elapsed=0;elapsed<tl;elapsed++){
        pid_t r=waitpid(ch,&st,WNOHANG);
        if(r>0)return WIFEXITED(st)?WEXITSTATUS(st):1;
        sleep(1);}
    fprintf(stderr,"\n\033[31m✗ TIMEOUT\033[0m: a once exceeded %us\n",tl);
    kill(ch,SIGKILL);waitpid(ch,NULL,0);return 124;}

/* ═══ DISPATCH TABLE — sorted for bsearch, every alias is one entry ═══ */
typedef struct { const char *n; int (*fn)(int, char**); } cmd_t;
static int cmd_cmp(const void *a, const void *b) {
    return strcmp(((const cmd_t *)a)->n, ((const cmd_t *)b)->n);
}
static const cmd_t CMDS[] = {
    {"--help",cmd_help_full},{"-h",cmd_help_full},
    {"a",cmd_all},{"adb",cmd_adb},{"add",cmd_add},{"agent",cmd_agent},{"ai",cmd_all},
    {"all",cmd_all},{"ask",cmd_ask},{"attach",cmd_attach},
    {"cat",cmd_cat},{"cleanup",cmd_cleanup},{"config",cmd_config},
    {"copy",cmd_copy},{"dash",cmd_dash},{"deps",cmd_deps},
    {"diff",cmd_diff},{"dir",cmd_dir},{"docs",cmd_docs},{"done",cmd_done},
    {"e",cmd_e},{"email",cmd_email},{"gdrive",cmd_gdrive},
    {"help",cmd_help_full},{"hi",cmd_hi},{"hub",cmd_hub},{"i",cmd_i},
    {"install",cmd_install},{"j",cmd_j},{"job",cmd_job},{"jobs",cmd_job},
    {"kill",cmd_kill},{"log",cmd_log},{"login",cmd_login},{"ls",cmd_ls},
    {"monolith",cmd_mono},{"move",cmd_move},
    {"n",cmd_note},{"note",cmd_note},{"once",cmd_run_once},
    {"p",cmd_push},{"perf",cmd_perf},{"pr",cmd_pr},{"prompt",cmd_prompt},
    {"pull",cmd_pull},{"push",cmd_push},
    {"remove",cmd_remove},{"repo",cmd_repo},{"revert",cmd_revert},{"review",cmd_review},
    {"rm",cmd_remove},{"run",cmd_run},{"scan",cmd_scan},{"send",cmd_send},
    {"set",cmd_set},{"settings",cmd_set},{"setup",cmd_setup},
    {"ssh",cmd_ssh},{"ssh add",cmd_ssh},{"ssh all",cmd_ssh},{"ssh rm",cmd_ssh},
    {"ssh self",cmd_ssh},{"ssh setup",cmd_ssh},{"ssh start",cmd_ssh},{"ssh stop",cmd_ssh},
    {"sync",cmd_sync},{"t",cmd_task},{"task",cmd_task},
    {"tree",cmd_tree},{"u",cmd_update},{"ui",cmd_ui},{"uninstall",cmd_uninstall},
    {"update",cmd_update},{"watch",cmd_watch},{"web",cmd_web},
    {"work",cmd_work},{"x",cmd_x},
};
#define NCMDS (sizeof(CMDS)/sizeof(*CMDS))

/* ═══ PERF KILL — hard timeout enforcer ═══ */
static char perf_msg[B]; /* pre-formatted kill message (signal-safe) */
__attribute__((noreturn)) static void perf_alarm(int sig) {
    (void)sig;
    (void)!write(STDERR_FILENO, perf_msg, strlen(perf_msg));
    kill(0, SIGTERM); _exit(124);
}
static void perf_arm(const char *cmd) {
    if (getenv("A_BENCH")) return; /* bench children: parent handles timeout */
    if (isdigit(*cmd)) return;
    static const char *skip[] = {"push","pull","sync","u","update","login","ssh","gdrive","mono","email","install","send","j","job","pr","hub",NULL};
    for (const char **p = skip; *p; p++) if (!strcmp(cmd, *p)) return;
    unsigned secs = 1;
    /* per-device override: adata/git/perf/{DEV}.txt — command:us (microseconds) */
    char pf[P]; snprintf(pf, P, "%s/perf/%s.txt", SROOT, DEV);
    unsigned limit_us = secs * 1000000;
    char *data = readf(pf, NULL);
    if (data) {
        char needle[128]; snprintf(needle, 128, "\n%s:", cmd);
        char *m = strstr(data, needle);
        if (!m && !strncmp(data, cmd, strlen(cmd)) && data[strlen(cmd)] == ':')
            m = data - 1;
        if (m) { unsigned us = (unsigned)atoi(m + 1 + strlen(cmd) + 1); if (us > 0) { limit_us = us; secs = (us + 999999) / 1000000; } }
        free(data);
    }
    snprintf(perf_msg, B,
        "\n\033[31m✗ PERF KILL\033[0m: 'a %s' exceeded %us timeout (limit: %uus, device: %s)\n"
        "  Fix: make it faster — timings only tighten, never loosen\n"
        "  Edit: %s\n", cmd, secs, limit_us, DEV, pf);
    signal(SIGALRM, perf_alarm);
    alarm(secs);
}
static void perf_disarm(void) { alarm(0); signal(SIGALRM, SIG_DFL); }

/* ═══ MAIN ═══ */
int main(int argc, char **argv) {
    init_paths();
    G_argc = argc; G_argv = argv;

    if (argc < 2) return cmd_help(argc, argv);

    /* Log every command */
    char acmd[B]="";for(int i=1,l=0;i<argc;i++) l+=snprintf(acmd+l,(size_t)(B-l),"%s%s",i>1?" ":"",argv[i]);
    char wd[P]; if(!getcwd(wd,P)) snprintf(wd,P,"%s",HOME);
    alog(acmd, wd, NULL);

    const char *arg = argv[1];

    /* "a 3" — jump to project by number (no perf: just cd) */
    { const char *p = arg; while (*p >= '0' && *p <= '9') p++;
      if (*p == '\0' && p != arg) { init_db(); return cmd_project_num(argc, argv, atoi(arg)); } }

    perf_arm(arg);

    /* Table lookup — O(log n) bsearch over sorted command table */
    { cmd_t key = {arg, NULL};
      const cmd_t *c = bsearch(&key, CMDS, NCMDS, sizeof(*CMDS), cmd_cmp);
      if (c) return c->fn(argc, argv); }

    /* "a x.foo" — experimental Python modules */
    if (arg[0] == 'x' && arg[1] == '.')
        { char mod[P]; snprintf(mod, P, "experimental/%s", arg + 2); fallback_py(mod, argc, argv); }

    /* "a c++" — create worktree for session key */
    { size_t l = strlen(arg);
      if (l >= 3 && arg[l-1] == '+' && arg[l-2] == '+' && arg[0] != 'w')
          return cmd_wt_plus(argc, argv); }

    /* "a wfoo" — w-prefix not in table = worktree */
    if (arg[0] == 'w' && !fexists(arg))
        return cmd_wt(argc, argv);

    /* "a c" — session key from sessions.txt */
    { init_db(); load_cfg(); load_sess();
      if (find_sess(arg)) return cmd_sess(argc, argv); }

    /* "a /some/path" or "a file.py" — open directory or file */
    if (dexists(arg) || fexists(arg)) return cmd_dir_file(argc, argv);
    { char ep[P]; snprintf(ep, P, "%s%s", HOME, arg);
      if (arg[0] == '/' && dexists(ep)) return cmd_dir_file(argc, argv); }

    /* 1-3 char keys not in table — try as session */
    if (strlen(arg) <= 3 && arg[0] >= 'a' && arg[0] <= 'z')
        return cmd_sess(argc, argv);

    /* "a job-foo-bar" — attach to existing tmux session by name */
    if (tm_has(arg)) { tm_go(arg); return 0; }

    /* Not a command — error in C, no silent Python fallback */
    fprintf(stderr, "a: '%s' is not a command. See 'a help'.\n", arg);
    return 1;
}
