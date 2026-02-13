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

[ -z "$BASH_VERSION" ] && exec bash "$0" "$@"
set -e
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

G='\033[32m' Y='\033[33m' C='\033[36m' R='\033[0m'
ok() { echo -e "${G}✓${R} $1"; }
info() { echo -e "${C}>${R} $1"; }
warn() { echo -e "${Y}!${R} $1"; }

_ensure_cc() {
    command -v clang &>/dev/null && { CC=clang; return 0; }
    command -v gcc &>/dev/null && { CC=gcc; return 0; }
    # Auto-install clang
    info "No C compiler found — installing clang..."
    if [[ -f /data/data/com.termux/files/usr/bin/bash ]]; then
        pkg install -y clang
    elif [[ -f /etc/debian_version ]]; then
        sudo apt-get install -y clang
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
    HARDEN="-fstack-protector-strong -ftrivial-auto-var-init=zero -fno-common"
    HARDEN+=" -D_FORTIFY_SOURCE=3 -fsanitize=safe-stack -fsanitize=cfi -fvisibility=hidden"
    [[ "$(uname)" != "Darwin" ]] && HARDEN+=" -fstack-clash-protection -fcf-protection=full"
}

_shell_funcs() {
    for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
        touch "$RC"
        grep -q '.local/bin' "$RC" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
        sed -i -e '/^a() {/,/^}/d' -e '/^aio() {/d' -e '/^ai() {/d' "$RC" 2>/dev/null||:
        cat >> "$RC" << 'AFUNC'
a() {
    local dd=~/.local/share/a
    [[ -z "$1" ]] && { [[ -f $dd/help_cache.txt ]] && printf '%s\n' "$(<"$dd/help_cache.txt")" || command a; return; }
    if [[ "$1" =~ ^[0-9]+$ ]]; then
        local -a lines; mapfile -t lines < $dd/projects.txt 2>/dev/null
        local dir="${lines[$1]}"; [[ -n "$dir" && -d "$dir" ]] && { printf '📂 %s\n' "$dir"; cd "$dir"; return; }
    fi
    local d="${1/#\~/$HOME}"; [[ "$1" == "/projects/"* ]] && d="$HOME$1"
    [[ -d "$d" ]] && { printf '📂 %s\n' "$d"; cd "$d"; return; }
    [[ "$1" == *.py && -f "$1" ]] && { local s=$(($(date +%s%N)/1000000)); python3 "$@"; local r=$?; echo "{\"cmd\":\"$1\",\"ms\":$(($(($(date +%s%N)/1000000))-s)),\"ts\":\"$(date -Iseconds)\"}" >> $dd/timing.jsonl; return $r; }
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
    SUDO=""
    if ! command -v tmux &>/dev/null || ! command -v npm &>/dev/null; then
        if [[ $EUID -eq 0 ]]; then SUDO=""
        elif sudo -n true 2>/dev/null; then SUDO="sudo"
        elif command -v sudo &>/dev/null && [[ -t 0 ]]; then info "sudo password needed for system packages"; sudo -v && SUDO="sudo"
        fi
    fi
    info "Detected: $OS ${SUDO:+(sudo)}${SUDO:-"(no root)"}"
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
    PIP_PKGS="pexpect prompt_toolkit"; [[ "$OS" == mac ]] && PIP_FLAGS="--break-system-packages" || PIP_FLAGS=""
    if command -v pip3 &>/dev/null; then pip3 install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras"
    elif command -v pip &>/dev/null; then pip install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras"
    elif command -v python3 &>/dev/null; then python3 -m ensurepip --user 2>/dev/null; python3 -m pip install --user $PIP_FLAGS -q $PIP_PKGS 2>/dev/null && ok "python extras" || warn "pip not available"; fi
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
    AROOT="$(dirname "$D")/adata"; SROOT="$AROOT/git"
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
 *   Dispatch — Linux syscall table: string→function pointer, same pattern.
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

#define P 1024
#define B 4096
#define MP 256
#define MA 64
#define MS 48

static void alog(const char *cmd, const char *cwd, const char *extra);

/* ═══ AMALGAMATION ═══ */
#include "lib/globals.c"
#include "lib/init.c"
#include "lib/util.c"
#include "lib/kv.c"
#include "lib/data.c"
#include "lib/tmux.c"
#include "lib/git.c"
#include "lib/session.c"
#include "lib/alog.c"
#include "lib/help.c"
#include "lib/project.c"
#include "lib/config.c"
#include "lib/push.c"
#include "lib/ls.c"
#include "lib/note.c"
#include "lib/ssh.c"
#include "lib/net.c"
#include "lib/agent.c"
#include "lib/sess.c"

/* ═══ MAIN DISPATCH ═══ */
int main(int argc, char **argv) {
    init_paths();
    G_argc = argc; G_argv = argv;

    if (argc < 2) return cmd_help(argc, argv);

    /* Log every command */
    char acmd[B]="";for(int i=1,l=0;i<argc;i++) l+=snprintf(acmd+l,(size_t)(B-l),"%s%s",i>1?" ":"",argv[i]);
    char wd[P]; if(!getcwd(wd,P)) snprintf(wd,P,"%s",HOME);
    alog(acmd, wd, NULL);

    const char *arg = argv[1];

    /* Numeric = project number */
    { const char *p = arg; while (*p >= '0' && *p <= '9') p++;
      if (*p == '\0' && p != arg) { init_db(); return cmd_project_num(argc, argv, atoi(arg)); } }

    /* Special aliases from CMDS dict */
    if (!strcmp(arg,"help")||!strcmp(arg,"hel")||!strcmp(arg,"--help")||!strcmp(arg,"-h"))
        return cmd_help_full(argc, argv);
    if (!strcmp(arg,"killall")) return cmd_kill(argc, argv);
    if (!strcmp(arg,"p")) return cmd_push(argc, argv);
    if (!strcmp(arg,"rm")) return cmd_remove(argc, argv);
    if (!strcmp(arg,"n")) return cmd_note(argc, argv);
    if (!strcmp(arg,"t")) return cmd_task(argc, argv);
    if (!strcmp(arg,"a")||!strcmp(arg,"ai")||!strcmp(arg,"aio")) return cmd_all(argc, argv);
    if (!strcmp(arg,"i")) return cmd_i(argc, argv);
    if (!strcmp(arg,"gdrive")||!strcmp(arg,"gdr")) fallback_py("gdrive", argc, argv);
    if (!strcmp(arg,"ask")) fallback_py("ask", argc, argv);
    if (!strcmp(arg,"ui")) fallback_py("ui/__init__", argc, argv);
    if (!strcmp(arg,"mono")||!strcmp(arg,"monolith")) fallback_py("mono", argc, argv);
    if (!strcmp(arg,"rebuild")) return cmd_rebuild();
    if (!strcmp(arg,"logs")) return cmd_log(argc, argv);

    /* Exact + alias match */
    if (!strcmp(arg,"push")||!strcmp(arg,"pus")) return cmd_push(argc, argv);
    if (!strcmp(arg,"pull")||!strcmp(arg,"pul")) return cmd_pull(argc, argv);
    if (!strcmp(arg,"diff")||!strcmp(arg,"dif")) return cmd_diff(argc, argv);
    if (!strcmp(arg,"revert")||!strcmp(arg,"rev")) return cmd_revert(argc, argv);
    if (!strcmp(arg,"ls")) return cmd_ls(argc, argv);
    if (!strcmp(arg,"kill")||!strcmp(arg,"kil")) return cmd_kill(argc, argv);
    if (!strcmp(arg,"config")||!strcmp(arg,"con")) return cmd_config(argc, argv);
    if (!strcmp(arg,"prompt")||!strcmp(arg,"pro")) return cmd_prompt(argc, argv);
    if (!strcmp(arg,"set")||!strcmp(arg,"settings")) return cmd_set(argc, argv);
    if (!strcmp(arg,"add")) return cmd_add(argc, argv);
    if (!strcmp(arg,"remove")||!strcmp(arg,"rem")) return cmd_remove(argc, argv);
    if (!strcmp(arg,"move")||!strcmp(arg,"mov")) return cmd_move(argc, argv);
    if (!strcmp(arg,"scan")||!strcmp(arg,"sca")) return cmd_scan(argc, argv);
    if (!strcmp(arg,"done")) return cmd_done();
    if (!strcmp(arg,"hi")) return cmd_hi();
    if (!strcmp(arg,"dir")) return cmd_dir();
    if (!strcmp(arg,"backup")||!strcmp(arg,"bak")) return cmd_backup();
    if (!strcmp(arg,"web")) return cmd_web(argc, argv);
    if (!strcmp(arg,"repo")) return cmd_repo(argc, argv);
    if (!strcmp(arg,"setup")||!strcmp(arg,"set up")) return cmd_setup(argc, argv);
    if (!strcmp(arg,"install")||!strcmp(arg,"ins")) return cmd_install();
    if (!strcmp(arg,"uninstall")||!strcmp(arg,"uni")) return cmd_uninstall();
    if (!strcmp(arg,"deps")||!strcmp(arg,"dep")) return cmd_deps();
    if (!strcmp(arg,"e")) return cmd_e(argc, argv);
    if (!strcmp(arg,"x")) return cmd_x();
    if (!strcmp(arg,"copy")||!strcmp(arg,"cop")) return cmd_copy();
    if (!strcmp(arg,"dash")||!strcmp(arg,"das")) return cmd_dash();
    if (!strcmp(arg,"attach")||!strcmp(arg,"att")) return cmd_attach(argc, argv);
    if (!strcmp(arg,"watch")||!strcmp(arg,"wat")) return cmd_watch(argc, argv);
    if (!strcmp(arg,"send")||!strcmp(arg,"sen")) return cmd_send(argc, argv);
    if (!strcmp(arg,"jobs")||!strcmp(arg,"job")) return cmd_jobs(argc, argv);
    if (!strcmp(arg,"cleanup")||!strcmp(arg,"cle")) return cmd_cleanup(argc, argv);
    if (!strcmp(arg,"tree")||!strcmp(arg,"tre")) return cmd_tree(argc, argv);
    if (!strcmp(arg,"note")) return cmd_note(argc, argv);
    if (!strcmp(arg,"task")||!strcmp(arg,"tas")) return cmd_task(argc, argv);
    if (!strcmp(arg,"ssh")) return cmd_ssh(argc, argv);
    if (!strcmp(arg,"hub")) return cmd_hub(argc, argv);
    if (!strcmp(arg,"log")) return cmd_log(argc, argv);
    if (!strcmp(arg,"login")) return cmd_login(argc, argv);
    if (!strcmp(arg,"sync")||!strcmp(arg,"syn")) return cmd_sync(argc, argv);
    if (!strcmp(arg,"update")||!strcmp(arg,"upd")) return cmd_update(argc, argv);
    if (!strcmp(arg,"review")) return cmd_review(argc, argv);
    if (!strcmp(arg,"docs")||!strcmp(arg,"doc")) return cmd_docs(argc, argv);
    if (!strcmp(arg,"run")) return cmd_run(argc, argv);
    if (!strcmp(arg,"agent")) return cmd_agent(argc, argv);
    if (!strcmp(arg,"work")||!strcmp(arg,"wor")) { fallback_py("work", argc, argv); }
    if (!strcmp(arg,"all")) return cmd_all(argc, argv);

    /* x.* experimental commands */
    if (arg[0] == 'x' && arg[1] == '.') {
        char mod[P]; snprintf(mod, P, "experimental/%s", arg + 2);
        fallback_py(mod, argc, argv);
    }

    /* Worktree: key++ */
    { size_t l = strlen(arg);
      if (l >= 3 && arg[l-1] == '+' && arg[l-2] == '+' && arg[0] != 'w')
          return cmd_wt_plus(argc, argv); }

    /* Worktree: w* */
    if (arg[0] == 'w' && strcmp(arg,"watch") && strcmp(arg,"web") && !fexists(arg))
        return cmd_wt(argc, argv);

    /* Directory or file */
    if (dexists(arg) || fexists(arg)) return cmd_dir_file(argc, argv);
    { char ep[P]; snprintf(ep, P, "%s%s", HOME, arg);
      if (arg[0] == '/' && dexists(ep)) return cmd_dir_file(argc, argv); }

    /* Session key check */
    { init_db(); load_cfg(); load_sess();
      if (find_sess(arg)) return cmd_sess(argc, argv); }

    /* Short session-like keys (1-3 chars) */
    if (strlen(arg) <= 3 && arg[0] >= 'a' && arg[0] <= 'z')
        return cmd_sess(argc, argv);

    /* Unknown - try python */
    fallback_py("sess", argc, argv);
}
