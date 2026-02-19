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
# CLAUDE CODE TERMUX WORKAROUND:
# Claude Code's sandbox treats "bash <script>" differently from direct
# commands. Running a script file triggers sandbox monitoring that tries
# to mkdir under /tmp. On Termux, /tmp is owned by "shell" (not the app
# user), so that mkdir fails and the script never starts.
# Direct commands (clang-21 ..., python3 ..., ./a help) skip that path
# and work fine. So: run the compiler directly instead of "bash a.c".
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
        sed -i -e '/^_ADD=/d' -e '/^a() {/,/^}/d' -e '/^aio() {/d' -e '/^ai() {/d' "$RC" 2>/dev/null||:
        echo "_ADD=\"$D/adata/local\"" >> "$RC"
        cat >> "$RC" << 'AFUNC'
a() {
    local dd="$_ADD"
    [[ -z "$1" ]] && { [[ -f $dd/help_cache.txt ]] && printf '%s\n' "$(<"$dd/help_cache.txt")" || command a; return; }
    if [[ "$1" =~ ^[0-9]+$ ]]; then
        local -a lines; mapfile -t lines < $dd/projects.txt 2>/dev/null
        local dir="${lines[$1]}"; [[ -n "$dir" && -d "$dir" ]] && { printf '📂 %s\n' "$dir"; cd "$dir"; return; }
    fi
    local d="${1/#\~/$HOME}"; [[ "$1" == "/projects/"* ]] && d="$HOME$1"
    [[ -d "$d" ]] && { printf '📂 %s\n' "$d"; cd "$d"; return; }
    [[ "$1" == *.py && -f "$1" ]] && { local py=python3 ev=1; [[ -n "$VIRTUAL_ENV" ]] && py="$VIRTUAL_ENV/bin/python" ev=0; [[ -x .venv/bin/python ]] && py=.venv/bin/python ev=0; local s=$(($(date +%s%N)/1000000)); if command -v uv &>/dev/null && [[ -f pyproject.toml || -f uv.lock ]]; then uv run python "$@"; ev=0; else $py "$@"; fi; local r=$?; echo "{\"cmd\":\"$1\",\"ms\":$(($(($(date +%s%N)/1000000))-s)),\"ts\":\"$(date -Iseconds)\"}" >> $dd/timing.jsonl; [[ $r -ne 0 && $ev -ne 0 ]] && printf '  try: a c fix python env for this project\n'; return $r; }
    command a "$@"; [[ -f $dd/cd_target ]] && { read -r d < $dd/cd_target; rm $dd/cd_target; cd "$d" 2>/dev/null; }
}
aio() { a "$@"; }
ai() { a "$@"; }
AFUNC
    done
    ok "shell functions (bash + zsh)"
}

case "${1:-build}" in
build)
    _ensure_cc
    _warn_flags
    $CC $WARN $HARDEN -DSRC="\"$D\"" -O3 -flto -fsyntax-only "$D/a.c" & P1=$!
    $CC -DSRC="\"$D\"" -isystem "$HOME/micromamba/include" -O3 -march=native -flto -w -o "$D/a" "$D/a.c" $LDFLAGS & P2=$!
    wait $P1 && wait $P2
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
        termux) pkg update -y && pkg install -y clang tmux nodejs git python openssh sshpass gh rclone && ok "pkgs" ;;
        *) install_node; warn "Unknown OS - install tmux manually" ;;
    esac
    _ensure_cc
    sh "$D/a.c" && ok "a compiled ($CC, $(wc -c < "$D/a") bytes)" || warn "Build failed"
    ln -sf "$D/a" "$BIN/a"
    [[ -f "$D/a-i" ]] && ln -sf "$D/a-i" "$BIN/a-i" && chmod +x "$BIN/a-i" && ok "a-i installed" || :
    E_SRC="$HOME/projects/editor/e.c"
    if [[ -f "$E_SRC" ]]; then
        $CC -w -o "$BIN/e" "$E_SRC" && ok "e editor (local)"
    else
        E_URL="https://raw.githubusercontent.com/seanpattencode/editor/main/e.c"
        curl -fsSL "$E_URL" -o /tmp/e.c && $CC -w -o "$BIN/e" /tmp/e.c && ok "e editor (remote)"
    fi
    _shell_funcs
    install_cli() {
        local pkg="$1" cmd="$2"
        if ! command -v "$cmd" &>/dev/null; then
            info "Installing $cmd..."
            if command -v npm &>/dev/null; then npm install -g "$pkg" && ok "$cmd" || warn "$cmd failed"
            else warn "$cmd skipped (npm not found)"; fi
        else ok "$cmd (exists)"; fi
    }
    install_cli "@anthropic-ai/claude-code" "claude"
    install_cli "@openai/codex" "codex"
    install_cli "@google/gemini-cli" "gemini"
    # Python venv — solves PEP 668 (externally-managed-environment).
    # Modern distros (Ubuntu 23.04+, Homebrew, Fedora 38+) block global pip
    # install. A venv in adata/ bypasses this cleanly: isolated, no sudo,
    # survives Python upgrades. fallback_py() in session.c tries the venv
    # python first, falls back to system python3 if missing.
    # _best_py picks the newest stable python that has the venv module.
    _best_py() {
        for v in python3.14 python3.13 python3.12 python3.11 python3; do command -v $v &>/dev/null && { $v -c 'import venv' 2>/dev/null && echo $v && return; }; done
    }
    VENV="$D/adata/venv"; PY=$(_best_py)
    if [[ -n "$PY" ]]; then
        if [[ ! -f "$VENV/bin/python" ]]; then
            info "Creating venv with $PY..."
            $PY -m venv "$VENV" && ok "venv ($($VENV/bin/python --version))" || warn "venv creation failed"
        else ok "venv (exists: $($VENV/bin/python --version))"; fi
        [[ -f "$VENV/bin/pip" ]] && $VENV/bin/pip install -q pexpect prompt_toolkit aiohttp 2>/dev/null && ok "python deps" || warn "pip install failed"
    else warn "python3 not found"; fi
    # UI auto-start service (launchd on mac, systemd on linux).
    # Always-on ~15MB: server starts at login, restarts on crash.
    # http://a.local:1111 just works. `a ui k` to disable.
    "$BIN/a" ui on >/dev/null 2>&1 && ok "UI service (http://a.local:1111)" || :
    if ! command -v ollama &>/dev/null; then
        if [[ -n "$SUDO" ]] || [[ $EUID -eq 0 ]]; then
            info "Installing ollama..."
            curl -fsSL https://ollama.com/install.sh | sh && ok "ollama" || warn "ollama install failed"
        else warn "ollama needs sudo - run: curl -fsSL https://ollama.com/install.sh | sudo sh"; fi
    else ok "ollama (exists)"; fi
    [[ ! -s "$HOME/.tmux.conf" ]] && "$BIN/a" config tmux_conf y 2>/dev/null && ok "tmux config (mouse enabled)" || :
    "$BIN/a" >/dev/null 2>&1 && ok "cache generated" || :
    command -v gh &>/dev/null && { gh auth status &>/dev/null || { [[ -t 0 ]] && info "GitHub login enables sync" && read -p "Login? (y/n): " yn && [[ "$yn" =~ ^[Yy] ]] && gh auth login && gh auth setup-git; }; gh auth status &>/dev/null && "$BIN/a" backup setup 2>/dev/null && ok "sync configured"; } || :
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
 * Add a command:  write lib/foo.c, add #include + dispatch line here.
 * Remove:         delete the file, delete two lines.
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
 *     context/                  agent context files (.txt, togglable)
 *     docs/                     user documents
 *   venv/                     Python venv — isolated deps (aiohttp, pexpect, etc)
 *                               Created by `a install`, refreshed by `a update`.
 *                               fallback_py() tries venv/bin/python first, then
 *                               system python3. Solves PEP 668 (Ubuntu 23.04+,
 *                               Homebrew) where global pip install is blocked.
 *   sync/                     rclone copy <->, all devices, large files <5G
 *   vault/                    rclone copy on-demand, big devices, models
 *   backup/                   rclone move ->, all devices, logs+state
 *     {device}/               LOGDIR — session logs ({device}__{session}.log)
 * ~/.local/bin/a              symlink to compiled binary
 */

#define P 1024
#define B 4096
#define MP 256
#define MA 64
#define MS 48

static void alog(const char *cmd, const char *cwd, const char *extra);

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
#include "lib/sess.c"     /* session dispatch (c/g/co/etc) */
#include "lib/ui_server.c" /* C WebSocket terminal (xterm.js) */

/* ═══ PY-ONLY WRAPPERS — C entry points for commands still in Python ═══ */
static int cmd_gdrive(int argc, char **argv) { fallback_py("gdrive", argc, argv); }
static int cmd_ask(int argc, char **argv)    { fallback_py("ask", argc, argv); }
static int cmd_ui(int argc, char **argv)     { fallback_py("ui/__init__", argc, argv); }
static int cmd_mono(int argc, char **argv)   { fallback_py("mono", argc, argv); }
static int cmd_work(int argc, char **argv)   { fallback_py("work", argc, argv); }

/* ═══ DISPATCH TABLE — sorted for bsearch, every alias is one entry ═══ */
typedef struct { const char *n; int (*fn)(int, char**); } cmd_t;
static int cmd_cmp(const void *a, const void *b) {
    return strcmp(((const cmd_t *)a)->n, ((const cmd_t *)b)->n);
}
static const cmd_t CMDS[] = {
    {"--help",cmd_help_full},{"-h",cmd_help_full},
    {"a",cmd_all},{"add",cmd_add},{"agent",cmd_agent},{"ai",cmd_all},
    {"aio",cmd_all},{"all",cmd_all},{"ask",cmd_ask},
    {"att",cmd_attach},{"attach",cmd_attach},
    {"bak",cmd_backup},{"backup",cmd_backup},
    {"cle",cmd_cleanup},{"cleanup",cmd_cleanup},
    {"con",cmd_config},{"config",cmd_config},
    {"cop",cmd_copy},{"copy",cmd_copy},
    {"das",cmd_dash},{"dash",cmd_dash},
    {"dep",cmd_deps},{"deps",cmd_deps},
    {"dif",cmd_diff},{"diff",cmd_diff},{"dir",cmd_dir},
    {"doc",cmd_docs},{"docs",cmd_docs},{"done",cmd_done},
    {"e",cmd_e},{"email",cmd_email},
    {"gdr",cmd_gdrive},{"gdrive",cmd_gdrive},
    {"hel",cmd_help_full},{"help",cmd_help_full},{"hi",cmd_hi},
    {"hub",cmd_hub},{"i",cmd_i},
    {"ins",cmd_install},{"install",cmd_install},
    {"job",cmd_jobs},{"jobs",cmd_jobs},
    {"kil",cmd_kill},{"kill",cmd_kill},{"killall",cmd_kill},
    {"log",cmd_log},{"login",cmd_login},{"logs",cmd_log},{"ls",cmd_ls},
    {"mono",cmd_mono},{"monolith",cmd_mono},
    {"mov",cmd_move},{"move",cmd_move},
    {"n",cmd_note},{"note",cmd_note},
    {"p",cmd_push},{"pro",cmd_prompt},{"prompt",cmd_prompt},
    {"pul",cmd_pull},{"pull",cmd_pull},{"pus",cmd_push},{"push",cmd_push},
    {"rebuild",cmd_rebuild},
    {"rem",cmd_remove},{"remove",cmd_remove},{"repo",cmd_repo},
    {"rev",cmd_revert},{"revert",cmd_revert},{"review",cmd_review},
    {"rm",cmd_remove},{"run",cmd_run},
    {"sca",cmd_scan},{"scan",cmd_scan},
    {"sen",cmd_send},{"send",cmd_send},
    {"set",cmd_set},{"settings",cmd_set},{"setup",cmd_setup},
    {"ssh",cmd_ssh},{"syn",cmd_sync},{"sync",cmd_sync},
    {"t",cmd_task},{"tas",cmd_task},{"task",cmd_task},
    {"tre",cmd_tree},{"tree",cmd_tree},
    {"ui",cmd_ui},{"ui-serve",cmd_ui_serve},{"uni",cmd_uninstall},{"uninstall",cmd_uninstall},
    {"upd",cmd_update},{"update",cmd_update},
    {"wat",cmd_watch},{"watch",cmd_watch},{"web",cmd_web},
    {"wor",cmd_work},{"work",cmd_work},{"x",cmd_x},
};
#define NCMDS (sizeof(CMDS)/sizeof(*CMDS))

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

    /* "a 3" — jump to project by number */
    { const char *p = arg; while (*p >= '0' && *p <= '9') p++;
      if (*p == '\0' && p != arg) { init_db(); return cmd_project_num(argc, argv, atoi(arg)); } }

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

    /* "a /some/path" or "a file.py" — open directory or file */
    if (dexists(arg) || fexists(arg)) return cmd_dir_file(argc, argv);
    { char ep[P]; snprintf(ep, P, "%s%s", HOME, arg);
      if (arg[0] == '/' && dexists(ep)) return cmd_dir_file(argc, argv); }

    /* "a c" — session key from sessions.txt */
    { init_db(); load_cfg(); load_sess();
      if (find_sess(arg)) return cmd_sess(argc, argv); }

    /* 1-3 char keys not in table — try as session */
    if (strlen(arg) <= 3 && arg[0] >= 'a' && arg[0] <= 'z')
        return cmd_sess(argc, argv);

    /* Not a command — error in C, no silent Python fallback */
    fprintf(stderr, "a: '%s' is not a command. See 'a help'.\n", arg);
    return 1;
}
