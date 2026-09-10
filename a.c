#if 0
# -- a.c - agent manager & human-AI accelerator. sh a.c [build|install|analyze|shell|clean]
# Polyglot: shell sees # as comments; C preprocessor skips #if 0..#endif.
# Fixes: fewer tokens, same speed+. Features: cut until it breaks.
# Read codebase: a cat [dir]: newest files first, whole under A_CB bytes (1.2MB = ~570k Fable tokens), 10-line stubs past it; header line says CONTEXT COMPLETE|INCOMPLETE; copies to clipboard
# Context: a c/j preloads a cat (auto mode 3) into claude's system prompt via --append-system-prompt-file
# TERMUX: set CLAUDE_CODE_TMPDIR=$HOME/.tmp; build with clang directly.
case "$0" in *a.c) [ -z "$BASH_VERSION" ] && exec bash "$0" "$@";; *)
    set -e; A="$HOME/a"
    [[ ! -t 0 ]] && { T="/tmp/_ainst$$.c"; curl -fsSL https://raw.githubusercontent.com/seanpattencode/a/main/a.c -o "$T"; exec sh "$T"; }
    # bootstrap git: ARCHITECTURE #40 - `curl ... | sh` must succeed on a bare OS with no prereqs.
    # detect package manager and install. sudo is auto-applied where root is needed.
    command -v git >/dev/null || { S=""; [ "$EUID" != 0 ] && command -v sudo >/dev/null && S="sudo"
        if [[ "$OSTYPE" == darwin* ]]; then command -v brew &>/dev/null || { /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"; }; brew install git &>/dev/null
        elif [ -f /data/data/com.termux/files/usr/bin/bash ]; then pkg install -y git
        elif [ -f /etc/debian_version ]; then $S apt-get update -qq && $S apt-get install -y git
        elif [ -f /etc/arch-release ]; then $S pacman -Sy --noconfirm git
        elif [ -f /etc/fedora-release ]; then $S dnf install -y git
        else echo "x unsupported OS — install git manually"; exit 1; fi
        command -v git >/dev/null || { echo "x git install failed"; exit 1; }; }
    [ -d "$A/.git" ] && { echo "a already installed at $A"; git -C "$A" pull --ff-only --quiet 2>/dev/null || :; exec sh "$A/a.c" install; }
    git clone https://github.com/seanpattencode/a.git "$A" && exec sh "$A/a.c" install
    exit 1;; esac
set -e
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

G='\033[32m' Y='\033[33m' C='\033[36m' R='\033[0m'
ok() { echo -e "${G}✓${R} $1"; }
info() { echo -e "${C}>${R} $1"; }
warn() { echo -e "${Y}!${R} $1"; }

_ensure_cc() {
    _cc_ok() { "$1" -x c -fsyntax-only /dev/null 2>/dev/null; }
    [[ "$OSTYPE" == darwin* && -x /opt/homebrew/opt/llvm/bin/clang ]] && { CC=/opt/homebrew/opt/llvm/bin/clang; return 0; }
    CC=$(compgen -c clang- 2>/dev/null|grep -xE 'clang-[0-9]+'|sort -t- -k2 -rn|head -1) || CC=""
    [[ -n "$CC" ]] && _cc_ok "$CC" && return 0; CC=""
    command -v clang &>/dev/null && _cc_ok clang && { CC=clang; return 0; }
    command -v tcc &>/dev/null && { CC=tcc; return 0; }
    info "Installing compiler..."
    if [[ -f /data/data/com.termux/files/usr/bin/bash ]]; then pkg install -y clang || true
    elif [[ -f /etc/debian_version ]]; then [[ -f "$D/adata/git/settings/dev" ]] && sudo find /etc/apt/sources.list.d -name '*llvm*' -delete 2>/dev/null; sudo apt-get update -qq && sudo apt-get install -y clang 2>/dev/null || true
    elif [[ -f /etc/arch-release ]]; then sudo pacman -S --noconfirm clang 2>/dev/null || true
    elif [[ -f /etc/fedora-release ]]; then sudo dnf install -y clang 2>/dev/null || true
    elif [[ "$OSTYPE" == darwin* ]]; then command -v brew &>/dev/null && brew install llvm 2>/dev/null && [[ -x /opt/homebrew/opt/llvm/bin/clang ]] && { CC=/opt/homebrew/opt/llvm/bin/clang; return 0; }; xcode-select --install 2>/dev/null; echo "Run 'xcode-select --install' and retry"; exit 1; fi
    command -v clang &>/dev/null && _cc_ok clang && { CC=clang; return 0; }
    command -v tcc &>/dev/null && { CC=tcc; return 0; }
    command -v gcc &>/dev/null && _cc_ok gcc && { warn "using gcc"; CC=gcc; return 0; }
    echo "ERROR: no compiler"; exit 1
}
_warn_flags() {
    if [[ "$CC" == *clang* ]]; then
        WARN="-std=c17 -Werror -Weverything -Wno-unknown-warning-option -Wno-padded -Wno-disabled-macro-expansion -Wno-reserved-id-macro -Wno-documentation -Wno-declaration-after-statement -Wno-unsafe-buffer-usage -Wno-used-but-marked-unused -Wno-pre-c11-compat -Wno-implicit-void-ptr-cast -Wno-nullable-to-nonnull-conversion -Wno-poison-system-directories -Wno-format-nonliteral -Wno-implicit-int-float-conversion -Wno-overlength-strings --system-header-prefix=/usr/include -isystem /usr/local/include"
    else WARN="-std=c17 -w"; fi
}
_shell_funcs() {
    for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
        touch "$RC" 2>/dev/null || { warn "can't write $RC (skip)"; continue; }
        grep -q '.local/bin' "$RC" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
        sed -i.bak '/^_ADD=/d;/^a() {/,/^}/d;/^aio() /d;/^ai() /d;/aios/d;/a-tmux-env-fix/,+1d' "$RC";rm "$RC.bak"
        _R="${D%%/adata/worktrees/*}"; _R="${_R%%/adata/forks/*}"
        echo "_ADD=\"$_R/adata/local\"" >> "$RC"
        cat >> "$RC" << 'AFUNC'
a() {
    local dd="$_ADD" d
    [[ "$1" == */* && -d "$1" ]] && { echo "📂 $1"; cd "$1"; return; }
    [[ "$1" == *.c && -f "$1" ]] && { sh "$@"; return; }
    [[ "$1" == *.py && -f "$1" ]] && { local py=python3 ev=1; [[ -n "$VIRTUAL_ENV" ]] && py="$VIRTUAL_ENV/bin/python" ev=0; [[ -x .venv/bin/python ]] && py=.venv/bin/python ev=0; local s=$(($(date +%s%N)/1000000)); if command -v uv &>/dev/null && [[ -f pyproject.toml || -f uv.lock ]]; then uv run python "$@"; ev=0; else $py "$@"; fi; local r=$?; echo "{\"cmd\":\"$1\",\"ms\":$(($(($(date +%s%N)/1000000))-s)),\"ts\":\"$(date -Iseconds)\"}" >> $dd/timing.jsonl; [[ $r -ne 0 && $ev -ne 0 ]] && printf '  try: a c fix python env for this project\n'; return $r; }
    [[ "$1" == kill && "$2" == all || "$1" == killall ]] && { { printf '%s a-sh %s tty=%s by: ' "$(date '+%F %T')" "$1" "$([[ -t 0 ]] && echo 1 || echo 0)"; ps -o args= -p $PPID 2>/dev/null | head -c100; echo; } >>"$HOME/a/adata/local/tmuxdeaths.log" 2>/dev/null; [[ -t 0 || "$3$2" == *now* ]] || { echo "x refused: headless tmux-server kill — append: now"; return 1; }; pkill -9 tmux 2>/dev/null; sleep 1; echo "✓"; return; }
    [[ "$1" == copy && -z "$2" && -z "$TMUX" && -t 0 ]] && { local lc; lc=$(fc -ln -2 -2 2>/dev/null); lc=${lc#"${lc%%[! ]*}"}; [[ "$lc" && "$lc" != a\ copy* ]] && { eval "$lc" 2>&1|command a copy; return; }; echo "x No prev cmd"; return 1; }
    command a "$@"; local r=$?; [[ $r -ne 0 && ( "$1" == update || "$1" == u ) ]] && { git -C "${dd%/adata/local}" pull --ff-only 2>/dev/null; sh "${dd%/adata/local}/a.c"; return; }; [[ -f $dd/cd_target ]] && { read -r d < $dd/cd_target; rm $dd/cd_target; cd "$d" 2>/dev/null; }; return $r
}
aio() { a "$@"; }
ai() { a "$@"; }
# a-tmux-env-fix: pull live graphical env from tmux global (session may explicitly unset DISPLAY/WAYLAND_DISPLAY); tmux global may lack it too (compositor never pushed it) -> probe the wayland socket
[ -n "$TMUX" ] && [ -z "$WAYLAND_DISPLAY$DISPLAY" ] && eval "$(tmux show-environment -g 2>/dev/null|grep -E '^(WAYLAND_DISPLAY|DISPLAY|DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR)='|sed 's/^/export /')"; [ -z "$WAYLAND_DISPLAY$DISPLAY" ] && for _s in "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"/wayland-*; do [ -S "$_s" ] && export WAYLAND_DISPLAY="${_s##*/}" && break; done
AFUNC
    done
    if [[ -d /data/data/com.termux ]]; then
        mkdir -p "$HOME/.tmp"
        grep -q CLAUDE_CODE_TMPDIR "$HOME/.bashrc" 2>/dev/null || echo 'export CLAUDE_CODE_TMPDIR="$HOME/.tmp"' >> "$HOME/.bashrc"
        tmux set-environment -g CLAUDE_CODE_TMPDIR "$HOME/.tmp" 2>/dev/null || :
    fi
    ok "shell funcs"
}
_install_node() {
    if [[ -d /data/data/com.termux ]]; then
        rm -f "$HOME/.local/bin/node" "$HOME/.local/bin/npm" "$HOME/.local/bin/npx"
        pkg install -y nodejs-lts 2>/dev/null||pkg install -y nodejs
        command -v node &>/dev/null&&ok "node $(node -v)"||warn "node failed"; return
    fi
    mkdir -p "$HOME/.local/bin"; export PATH="$HOME/.local/bin:$PATH"
    ARCH=$(uname -m); [[ "$ARCH" == "x86_64" ]] && ARCH="x64"; [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]] && ARCH="arm64"
    if [[ "$OSTYPE" == darwin* ]]; then URL="https://nodejs.org/dist/v22.12.0/node-v22.12.0-darwin-$ARCH.tar.gz"
    else URL="https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-$ARCH.tar.xz"; fi
    info "Installing node v22.12.0 ($ARCH)..."
    if [[ "$URL" == *.gz ]]; then curl -fsSL "$URL" | tar -xzf - -C "$HOME/.local" --strip-components=1
    else curl -fsSL "$URL" | tar -xJf - -C "$HOME/.local" --strip-components=1; fi
    [[ -x "$HOME/.local/bin/node" ]] && ok "node $($HOME/.local/bin/node -v)" || warn "node install failed"
}
_perf_lim() { local f="$D/adata/git/perf/$(cat "$D/adata/local/.device" 2>/dev/null||cat "$D/adata/local/device.txt" 2>/dev/null||hostname 2>/dev/null||echo unknown).txt"
    local v;v=$(grep "^$1:" "$f" 2>/dev/null)&&echo "${v#*:}"||echo 0;}
_perf_chk() { local e=$(( ${EPOCHREALTIME/./} - _PT )) l=$(_perf_lim "$1")
    [[ $l -gt 0 && $e -gt $l ]] && { echo -e "\033[31m✗ PERF KILL\033[0m: sh a.c $1 ${e}us > ${l}us" >&2; exit 1; }
    echo -e "${e}us" >&2;}
_tok_chk() { local f="$D/adata/git/perf/tok.txt" t c;c=$(head -1 "$f" 2>/dev/null||:)  # entropy deadman: human-only cap, see warning in file
    [[ "$c" =~ ^[0-9]+$ ]] || c=300000  # no cap file → hardcoded floor; never fail open
    t=$(( $(git -C "$D" ls-files -z a.c lib 2>/dev/null|xargs -0 cat 2>/dev/null|wc -c)/4 ))
    echo "tok $t/$c ($(( t<=c ? c-t : t-c )) $([[ $t -le $c ]] && echo left || echo over))" >&2
    [[ $t -le $c ]] || { echo -e "\033[31m✗ TOK KILL\033[0m: a.c+lib = $t > cap $c tok — simplify, don't raise ($f)" >&2;sed 1d "$f" >&2 2>/dev/null;exit 1; };}
_Q=-DSRC="\"$D\"";[[ -d /data/data/com.termux ]]&&_QT=--target=aarch64-linux-android30
_abin() { [[ "$D" == *"/adata/worktrees/"*||"$D" == *"/adata/forks/"* ]]&&ABIN="$D"||ABIN="$D/adata/local"
    BIN="$HOME/.local/bin";mkdir -p "$ABIN" "$BIN";}
_checkers() {
    _c(){ n=$1;shift;{ ! command -v "$1" &>/dev/null||"$@";}>"$T/$n" 2>&1||touch "$T/$n.f";}
    _rgcc(){ command -v gcc &>/dev/null&&! gcc --version 2>&1|grep -q clang;}
    _c 1 $CC $WARN $A -fsyntax-only "$F" &
    _c 3 clang-tidy --checks='-*,bugprone-branch-clone,bugprone-infinite-loop,bugprone-sizeof-*' -warnings-as-errors='*' "$F" -- $A -std=c17 -w &
    { ! _rgcc||gcc -std=c17 -Werror=logical-op -Werror=duplicated-cond -Werror=duplicated-branches -Werror=trampolines $A -fsyntax-only "$F";}>"$T/4" 2>&1||touch "$T/4.f" &
    { mkdir -p "$T/s/lib";cd "$D"&&for f in a.c lib/*.c;do awk '/^#if 0/{s=1}s{if(/^#endif/)s=0;print"";next}1' $f>"$T/s/$f";done;cd "$T/s"&&_c 6 cppcheck --error-exitcode=1 -q --suppress=memleakOnRealloc $A a.c;} & _c 7 frama-c -eva -eva-no-print -no-unicode -cpp-extra-args="$A" "$F" &
{ $CC $A -fsanitize=undefined,address -fno-omit-frame-pointer -w -o "$T/a.san" "$F"&&A_BENCH=1 "$T/a.san" help >"$T/9" 2>&1;! grep -q 'runtime error\|SUMMARY:.*Sanitizer' "$T/9";}||touch "$T/9.f" &
    { ! command -v infer &>/dev/null||{ infer run --no-progress-bar -o "$T/infer" -- clang $A -w -c "$F" -o /dev/null >"$T/10" 2>&1;! grep -q 'NULLPTR_DEREFERENCE\|BUFFER_OVERRUN\|USE_AFTER_FREE' "$T/infer/report.txt" 2>/dev/null;};}||touch "$T/10.f" &
    wait
}
_o3(){ $CC $A -O3 -march=native -static -w -o "$ABIN/a.opt" "$F" -lutil 2>/dev/null||{ command -v musl-gcc>/dev/null&&musl-gcc -std=gnu11 -D_GNU_SOURCE -O3 -march=native -static -w -o "$ABIN/a.opt" "$F" -lutil 2>/dev/null;}||$CC $A -O3 -march=native -w -o "$ABIN/a.opt" "$F" -lutil;}  # glibc-static first: SIMD str*/stdio = 2.1x faster i render than musl (measured 7/5); musl fallback
case "${1:-build}" in
node) N="$HOME/.local/bin/node"; [[ -x "$N" ]] && V="$("$N" -v)" && [[ "$V" == v2[2-9]* || "$V" == v[3-9]* ]] && { ok "node $V"; exit 0; }; _install_node ;;
build) _PT=${EPOCHREALTIME/./};_tok_chk
    _abin; rm -f "$ABIN/.chk" "$ABIN/i_cache.txt"
    printf '%s' $$ > "$ABIN/.bld"
    _build_fix() {
        warn "Build failed, attempting fix..."
        command -v a &>/dev/null && { a j --no-wt "a.c compile error: $1. Fix and run 'sh a.c'."; return; }
        echo "Couldn't auto-fix. github:seanpattencode"
    }
    if command -v tcc &>/dev/null && [[ ! -d /data/data/com.termux ]]; then
        # old tcc (0.9.27) dies on odd ' counts inside #if 0 (book.c py half) - fall back to $CC before calling the fix agent
        TCT=${EPOCHREALTIME/./};tcc $_Q -w -o "$ABIN/a" "$D/a.c" -lutil 2>/dev/null&&TCT=$(( ${EPOCHREALTIME/./} - TCT ))000||{ TCT="";_ensure_cc;E=$($CC $_Q -w -O0 -o "$ABIN/a" "$D/a.c" -lutil 2>&1)||{ _build_fix "$E"; exit 1; }; }
    else
        _ensure_cc; E=$($CC $_Q $_QT -w -O0 -o "$ABIN/a" "$D/a.c" -lutil 2>&1) || { _build_fix "$E"; exit 1; }
    fi
    [[ "$ABIN" == */adata/local ]] && { ln -sf "$ABIN/a" "$BIN/a"; ln -sf "$ABIN/a" "$BIN/h"; [[ -d /data/data/com.termux/files/usr/bin ]]&&{ ln -sf "$ABIN/a" /data/data/com.termux/files/usr/bin/a; ln -sf "$ABIN/a" /data/data/com.termux/files/usr/bin/h; }; }; _perf_chk build
    [[ -d /data/data/com.termux ]]&&/system/bin/cmd package query-activities --brief --user 0 -a android.intent.action.MAIN -c android.intent.category.LAUNCHER 2>/dev/null|awk '/\//{gsub(/^ +/,"");p=$0;sub(/\/.*/,"",p);sub(/.*\./,"",p);printf"open %s\t%s · app\n",$0,p}'>$ABIN/apps.txt&
    (
        T=$(mktemp -d);trap "rm -rf $T" EXIT;F="$D/a.c";A="$_Q $_QT"
        if [[ -n "$TCT" ]]; then
            PYT=$(date +%s%N);python3 -c 'import subprocess;subprocess.run(["echo","hello world"],capture_output=True)';PYT=$(( $(date +%s%N)-PYT ))
            [[ $TCT -gt $PYT ]] && { echo "PERF KILL: tcc ${TCT}ns > python ${PYT}ns" >"$ABIN/.chk"; touch "$T/0.f"; }
        fi
        _ensure_cc; _warn_flags
        _checkers
        if ls "$T"/*.f &>/dev/null;then cat "$T"/[0-9]* >"$ABIN/.chk" 2>/dev/null
            [ "$(cat "$ABIN/.bld" 2>&-)" = "$$" ]&&printf '#!/bin/sh\nhead -80 %s/.chk;exit 1' "$ABIN">"$ABIN/a"&&chmod +x "$ABIN/a"
        else _o3&&[ "$(cat "$ABIN/.bld" 2>&-)" = "$$" ]&&mv "$ABIN/a.opt" "$ABIN/a" 2>&-&&("$ABIN/a" ui reload >/dev/null 2>&1 &);rm -f "$ABIN/a.opt"
        fi
    ) >&- 2>&- &
    ;;
check) _PT=${EPOCHREALTIME/./};_tok_chk
    _abin; _ensure_cc; E=$($CC $_Q $_QT -w -O0 -o "$ABIN/a" "$D/a.c" -lutil 2>&1) || { echo "$E"; exit 1; }
    [[ "$ABIN" == */adata/local ]] && { ln -sf "$ABIN/a" "$BIN/a"; ln -sf "$ABIN/a" "$BIN/h"; [[ -d /data/data/com.termux/files/usr/bin ]]&&{ ln -sf "$ABIN/a" /data/data/com.termux/files/usr/bin/a; ln -sf "$ABIN/a" /data/data/com.termux/files/usr/bin/h; }; }
    T=$(mktemp -d);trap "rm -rf $T" EXIT;F="$D/a.c";A="$_Q";_warn_flags
    _checkers
    if ls "$T"/*.f &>/dev/null;then cat "$T"/[0-9]* 2>/dev/null; exit 1
    else ok "all checkers passed"; _perf_chk check; _o3&&mv "$ABIN/a.opt" "$ABIN/a" 2>&-&&("$ABIN/a" ui reload >/dev/null 2>&1 &);rm -f "$ABIN/a.opt" & fi
    ;;
analyze) _ensure_cc;_warn_flags
    $CC $WARN $_Q --analyze -Xanalyzer -analyzer-output=text -Xanalyzer -analyzer-checker=security,unix,nullability,optin.portability.UnixAPI -Xanalyzer -analyzer-disable-checker=security.insecureAPI.DeprecatedOrUnsafeBufferHandling "$D/a.c"
    find "$D" -maxdepth 1 -name '*.plist' -delete;;
shell) _shell_funcs;;
clean) rm -f "$D/adata/local/a";;
keys) bash "$D/lib/keys.c" "${2:-on}";;
install)
    BIN="$HOME/.local/bin"; mkdir -p "$BIN"; export PATH="$BIN:$PATH"
    if [[ "$OSTYPE" == darwin* ]]; then OS=mac
    elif [[ -f /data/data/com.termux/files/usr/bin/bash ]]; then OS=termux
    elif [[ -f /etc/debian_version ]]; then OS=debian
    elif [[ -f /etc/arch-release ]]; then OS=arch
    elif [[ -f /etc/fedora-release ]]; then OS=fedora
    else OS=unknown; fi
    _want() { [[ $# -eq 0 ]] && return 0; local i; for i in "$@"; do [[ "$i" == "$1" ]] && return 0; done; return 1; }
    shift; SEL=("$@")
    _w() { [[ ${#SEL[@]} -eq 0 ]] || { local t; for t in "${SEL[@]}"; do [[ "$t" == "$1" ]] && return 0; done; return 1; }; }
    _brew_ensure() { command -v brew &>/dev/null && return 0; info "Installing Homebrew..."; /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"; }
    _brew_pkg() { _brew_ensure && { brew install "$@" 2>/dev/null || brew upgrade "$@" 2>/dev/null; } && ok "$*"; }
    SUDO="" NEED_SUDO=0
    if [[ ${#SEL[@]} -eq 0 ]]; then
        { command -v tmux &>/dev/null && command -v npm &>/dev/null && grep -q 'a\.local' /etc/hosts 2>/dev/null; } || NEED_SUDO=1
        if [[ $EUID -eq 0 ]]; then SUDO=""
        elif sudo -n true 2>/dev/null; then SUDO="sudo"
        elif [[ $NEED_SUDO -eq 1 ]] && command -v sudo &>/dev/null && [[ -t 0 ]]; then info "sudo needed for system packages + /etc/hosts"; sudo -v && SUDO="sudo"
        fi
    fi
    info "Detected: $OS${SEL:+ [${SEL[*]}]} ${SUDO:+(sudo)}${SUDO:-"(no root)"}"
    if [[ ${#SEL[@]} -gt 0 ]]; then
        for pkg in "${SEL[@]}"; do
            case $pkg in
                brew) _brew_ensure ;;
                node) _w node && { local v;v=$(node -v 2>/dev/null)&&[[ "$v" == v2[2-9]*||"$v" == v[3-9]* ]]&&ok "node $v"||_install_node; } ;;
                claude) command -v claude &>/dev/null&&ok "claude"||{ curl -fsSL https://claude.ai/install.sh|bash&&ok "claude"||warn "claude failed"; } ;;
                uv) command -v uv &>/dev/null&&ok "uv"||{ curl -LsSf https://astral.sh/uv/install.sh|sh&&export PATH="$HOME/.local/bin:$PATH"&&ok "uv"||warn "uv failed"; } ;;
                ollama) command -v ollama &>/dev/null&&ok "ollama"||{ curl -fsSL https://ollama.com/install.sh|sh&&ok "ollama"||warn "ollama failed"; } ;;
                shell) _shell_funcs ;;
                build) _ensure_cc; sh "$D/a.c" && ok "a compiled" || warn "Build failed" ;;
                *) case $OS in
                    mac) _brew_pkg "$pkg" ;;
                    debian) sudo apt-get install -yqq "$pkg" 2>/dev/null && ok "$pkg" || warn "$pkg" ;;
                    arch) sudo pacman -S --noconfirm "$pkg" 2>/dev/null && ok "$pkg" || warn "$pkg" ;;
                    fedora) sudo dnf install -y "$pkg" 2>/dev/null && ok "$pkg" || warn "$pkg" ;;
                    termux) pkg install -y "$pkg" && ok "$pkg" || warn "$pkg" ;;
                    esac ;;
            esac
        done
        exit 0
    fi
    if ! grep -q 'a\.local' /etc/hosts 2>/dev/null; then
        if [[ -n "$SUDO" || $EUID -eq 0 ]]; then echo '127.0.0.1 a.local'|$SUDO tee -a /etc/hosts>/dev/null&&ok "a.local"
        elif [[ "$OS" == termux ]]; then ok "a.local (termux: use localhost:1111)"
        else warn "a.local: run 'echo 127.0.0.1 a.local | sudo tee -a /etc/hosts'"; fi
    else ok "a.local"; fi
    install_node() { local v;v=$(node -v 2>/dev/null)&&[[ "$v" == v2[2-9]*||"$v" == v[3-9]* ]]&&return 0;_install_node; }
    case $OS in
        mac)
            _brew_ensure
            brew tap hudochenkov/sshpass 2>/dev/null; brew install git llvm tmux node gh sshpass rclone cppcheck gcc python cliclick &>/dev/null||brew upgrade git llvm tmux node gh sshpass rclone cppcheck gcc python cliclick &>/dev/null
            /opt/homebrew/bin/python3 -m pip install -q --break-system-packages pyobjc-framework-Quartz 2>/dev/null
            command -v clang &>/dev/null || { xcode-select --install 2>/dev/null; warn "Run 'xcode-select --install' then retry"; }
            sh "$D/lib/keys.c" on 2>/dev/null || :
            ok "tmux + node + gh + rclone" ;;
        debian)
            if [[ -n "$SUDO" ]]; then export DEBIAN_FRONTEND=noninteractive
                $SUDO apt update -qq && $SUDO apt install -yqq clang libclang-rt-dev tmux git curl python3-pip sshpass rclone rsync tcc gcc cppcheck adb 2>/dev/null; $SUDO apt install -yqq cbmc frama-c-base 2>/dev/null || true
                command -v gh &>/dev/null||{ curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg|$SUDO tee /etc/apt/keyrings/gh.gpg>/dev/null&&echo "deb [signed-by=/etc/apt/keyrings/gh.gpg] https://cli.github.com/packages stable main"|$SUDO tee /etc/apt/sources.list.d/gh.list>/dev/null&&$SUDO apt update -qq&&$SUDO apt install -yqq gh;}||true; ok "pkgs"
                command -v infer &>/dev/null||{ V="v1.2.0";curl -sSL "https://github.com/facebook/infer/releases/download/$V/infer-linux-x86_64-$V.tar.xz"|tar -xJ -C /tmp/&&$SUDO mv "/tmp/infer-linux-x86_64-$V" /usr/local/lib/infer&&$SUDO ln -sf /usr/local/lib/infer/bin/infer /usr/local/bin/infer&&ok "infer"||warn "infer";}
            fi; install_node; [[ -z "$SUDO" ]] && { command -v tmux &>/dev/null || warn "tmux needs: sudo apt install tmux"; } ;;
        arch)
            if [[ -n "$SUDO" ]]; then $SUDO pacman -Sy --noconfirm clang tmux nodejs npm git python-pip sshpass rclone rsync github-cli tcc gcc cppcheck cbmc frama-c android-tools 2>/dev/null && ok "pkgs"
            else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo pacman -S tmux"; fi ;;
        fedora)
            # Two-step install: core (must succeed) then optional analyzers (best-effort).
            # cbmc/frama-c on Fedora pull in 500+ pkgs (Coq/OCaml/etc) and OOM small VMs;
            # tcc isn't in default Fedora repos. --skip-unavailable + --setopt=install_weak_deps=False
            # keeps the optional step bounded. Without splitting, one missing pkg aborted the
            # whole transaction and left node/zstd uninstalled.
            if [[ -n "$SUDO" ]]; then $SUDO dnf install -y --skip-unavailable clang tmux nodejs npm git curl gcc gh zstd android-tools 2>/dev/null && ok "pkgs"
                $SUDO dnf install -y --skip-unavailable --setopt=install_weak_deps=False python3-pip sshpass rclone rsync tcc cppcheck cbmc frama-c 2>/dev/null || :
            else install_node; command -v tmux &>/dev/null || warn "tmux needs: sudo dnf install tmux"; fi ;;
        termux) pkg update -y && pkg upgrade -y -o Dpkg::Options::=--force-confold && pkg install -y build-essential tcc tmux nodejs git python openssh sshpass fzf gh rclone rsync cronie termux-services android-tools ffmpeg && mkdir -p ~/.gyp && echo "{'variables':{'android_ndk_path':''}}" > ~/.gyp/include.gypi && ok "pkgs" ;;
        *) install_node; warn "Unknown OS - install tmux manually" ;;
    esac
    _ensure_cc
    sh "$D/a.c" && ok "a compiled" || warn "Build failed"
    E="$HOME/e"
    [[ -f "$E/e.c" ]] || git clone https://github.com/seanpattencode/e "$E" 2>/dev/null || :
    [[ -f "$E/e.c" ]] && sh "$E/e.c" install || :
    _shell_funcs
    [[ "$OS" == debian || "$OS" == arch || "$OS" == fedora ]] && { mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps; printf '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12"/><text x="32" y="50" font-family="monospace" font-size="52" fill="#fff" text-anchor="middle">a</text></svg>' >~/.local/share/icons/hicolor/scalable/apps/a.svg; printf '[Desktop Entry]\nType=Application\nName=a\nComment=agent manager\nExec=a\nTerminal=true\nIcon=a\nCategories=Development;\n' >~/.local/share/applications/a.desktop; ok "app icon"; }  # launcher icon so users SEE a exists (Sean 2026-08-23); mac/windows next
    install_cli() {
        local pkg="$1" cmd="$2" p=$(command -v "$cmd" 2>/dev/null)
        [[ -n "$p" && "${p:0:5}" != "/mnt/" ]] && "$cmd" --version &>/dev/null && { ok "$cmd"; return; }
        [[ -n "$p" ]] && warn "$cmd broken ($p), reinstalling"; info "Installing $cmd..."
        if ! command -v npm &>/dev/null; then warn "$cmd skipped (no npm)"
        else local ns=""; [[ -z "$SUDO" && $EUID -ne 0 && "$OS" != termux ]] && ns="--prefix=$HOME/.local"; $SUDO npm install -g $ns "$pkg"&&ok "$cmd"||warn "$cmd failed"; fi
    }
    _cok(){ command -v claude &>/dev/null && claude --version 2>&1|grep -q 'Claude Code'; }
    _cok&&ok "claude"||{ info "Installing claude...";curl -fsSL https://claude.ai/install.sh|bash||:
        [[ "$OS" == termux ]] && { pkg install -y glibc-repo glibc-runner 2>&1|tail -1||:
            nb=$(ls -t $HOME/.claude/downloads/claude-*-linux-*|head -1)
            [[ -n "$nb" ]] && mkdir -p $HOME/.local/bin && printf '#!/data/data/com.termux/files/usr/bin/sh\nexec grun %q "$@"\n' "$nb" > $HOME/.local/bin/claude && chmod +x $HOME/.local/bin/claude && info "wrapped: grun $nb"; }
        _cok&&ok "claude"||warn "claude failed";}
    python3 -c 'import json,os;p=os.path.expanduser("~/.claude/settings.json");os.makedirs(os.path.dirname(p),exist_ok=True);d=json.load(open(p)) if os.path.exists(p) else {};d["effortLevel"]="xhigh";json.dump(d,open(p,"w"),indent=2)' 2>/dev/null && ok "effort=xhigh"
    install_cli "$([[ $OS == termux ]] && echo @mmmbuto/codex-cli-termux || echo @openai/codex)" "codex"
    install_cli "@google/gemini-cli" "gemini" scripts
    [[ "$OS" == termux ]] && info "Gemini auth: NO_BROWSER=true gemini"
    command -v uv &>/dev/null&&ok "uv"||{ info "Installing uv...";curl -LsSf https://astral.sh/uv/install.sh|sh&&export PATH="$HOME/.local/bin:$PATH"&&ok "uv"||warn "uv failed";}
    if ! command -v uv &>/dev/null; then
        _best_py(){ for v in python3.14 python3.13 python3.12 python3.11 python3;do command -v $v &>/dev/null&&$v -c 'import venv' 2>/dev/null&&echo $v&&return;done;}
        VENV="$D/adata/venv";PY=$(_best_py)
        [[ -n "$PY" ]]&&{ [[ -f "$VENV/bin/python" ]]&&ok "venv"||{ $PY -m venv "$VENV"&&ok "venv"||warn "venv failed";}
        [[ -f "$VENV/bin/pip" ]]&&$VENV/bin/pip install -q pexpect prompt_toolkit aiohttp 2>/dev/null&&ok "python deps"||warn "pip failed";}
    fi
    if ! python3 -c "from playwright.sync_api import sync_playwright;sync_playwright().start().chromium.launch(headless=True).close()" 2>/dev/null; then
        info "Installing playwright browser deps..."
        if command -v pacman &>/dev/null; then sudo pacman -S --noconfirm --needed libxcomposite gtk3 alsa-lib nss 2>/dev/null && ok "playwright deps" || warn "playwright deps"
        elif command -v apt-get &>/dev/null; then sudo apt-get install -y libxcomposite1 libgtk-3-0t64 libasound2t64 libnss3 2>/dev/null && ok "playwright deps" || warn "playwright deps"; fi
    else ok "playwright deps"; fi
    command -v ollama &>/dev/null&&ok "ollama"||{ [[ -n "$SUDO" || $EUID -eq 0 ]]&&{ info "Installing ollama...";curl -fsSL https://ollama.com/install.sh|sh&&ok "ollama"||warn "ollama failed";}||warn "ollama needs sudo";}
    command -v gh &>/dev/null&&ok "gh"||[[ "$OS" == termux ]]||{ info "Installing gh...";A_=$(uname -m);[[ "$A_" == x86_64 ]]&&A_=amd64;[[ "$A_" == aarch64||"$A_" == arm64 ]]&&A_=arm64;O_=linux;[[ "$OSTYPE" == darwin* ]]&&O_=macOS;V_=$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest 2>/dev/null|grep -m1 tag_name|cut -d\" -f4|tr -d v);[[ -z "$V_" ]]&&V_=2.63.2;T_=$(mktemp -d);curl -fsSL "https://github.com/cli/cli/releases/download/v$V_/gh_${V_}_${O_}_${A_}.tar.gz"|tar -xzf - -C "$T_"&&mv "$T_"/*/bin/gh "$HOME/.local/bin/gh" 2>/dev/null&&ok "gh $V_"||warn "gh failed";rm -rf "$T_";}
    "$BIN/a" ui on 2>/dev/null && ok "UI service (localhost:1111)" || :
    [[ ! -s "$HOME/.tmux.conf" ]] && "$BIN/a" config tmux_conf y 2>/dev/null && ok "tmux config (mouse enabled)" || :
    "$BIN/a" >/dev/null 2>&1 && ok "cache generated" || :
    # 8s timeout on the gh-login prompt: ssh -tt forwards a tty so `[[ -t 0 ]]` is true even when
    # no human is attached (curl|sh through automation, CI, agent-spawned bootstrap). Without the
    # timeout, read blocks forever and eventually crashes the VM via stuck process.
    command -v gh &>/dev/null && { gh auth status &>/dev/null || { [[ -t 0 ]] && info "GitHub login enables sync" && { read -t 8 -p "Login? (y/n) [8s]: " yn || yn=n; } && [[ "$yn" =~ ^[Yy] ]] && gh auth login && gh auth setup-git; }; gh auth status &>/dev/null && ok "sync configured"; } || :
    AROOT="$D/adata"; SROOT="$AROOT/git"
    if [[ ! -d "$SROOT/.git" ]]; then mkdir -p "$AROOT"
        { command -v gh &>/dev/null&&gh auth status &>/dev/null 2>&1&&gh repo clone seanpattencode/a-git "$SROOT" 2>/dev/null&&ok "adata/git cloned";}||{ git init -q "$SROOT" 2>/dev/null;ok "adata/git init";}
    elif command -v gh &>/dev/null&&gh auth status &>/dev/null 2>&1; then
        ur=$(git -C "$SROOT" remote get-url origin 2>/dev/null)
        if [[ "$ur" != *a-git* ]]; then rm -rf "$SROOT"; gh repo clone seanpattencode/a-git "$SROOT" 2>/dev/null&&ok "adata/git re-cloned"
        else git -C "$SROOT" pull --ff-only -q 2>/dev/null&&ok "adata/git synced"||ok "adata/git"; fi
    fi
    # tame adata/git repacks: freeze >200m base pack + no reactive maintenance (HDD repack-storm fix)
    [[ -d "$SROOT/.git" ]]&&{ git -C "$SROOT" config maintenance.auto false;git -C "$SROOT" config gc.bigPackThreshold 200m;git -C "$SROOT" config fetch.unpackLimit 1;ok "adata/git tuned";}
    # install synced fleet ssh key so `a ssh <host>` authenticates out-of-box (don't clobber an existing device key)
    [[ -f "$SROOT/ssh/id_ed25519" && ! -f "$HOME/.ssh/id_ed25519" ]]&&{ mkdir -p "$HOME/.ssh";cp "$SROOT/ssh/id_ed25519" "$SROOT/ssh/id_ed25519.pub" "$HOME/.ssh/" 2>/dev/null;chmod 600 "$HOME/.ssh/id_ed25519";ok "fleet ssh key";}
    # extra user repos: adata/git/repos.txt - one "owner/name [target]" per line, '#' comments ok.
    # rationale: `a clone` brings `a` itself, but the user's personal repos (updater, trading,
    # research) don't ride along. manifest lives in adata so it syncs across the fleet -> a new
    # device's `a install` ends up with the same user repos. scope-bounded to git clone only;
    # any per-repo setup lives inside that repo (run it via `a hub` or its own bootstrap).
    [[ -f "$SROOT/repos.txt" ]]&&while IFS= read -r ln;do ln="${ln%%#*}";set -- $ln;[[ -z "$1" ]]&&continue
        tgt="${2:-$HOME/${1##*/}}";tgt="${tgt/#\~/$HOME}";[[ -d "$tgt/.git" ]]&&continue
        info "clone $1 -> $tgt"
        { command -v gh &>/dev/null&&gh auth status &>/dev/null 2>&1&&gh repo clone "$1" "$tgt" 2>/dev/null; }||git clone "https://github.com/$1.git" "$tgt" 2>/dev/null
        [[ -d "$tgt/.git" ]]&&ok "$1"||warn "$1"
    done < "$SROOT/repos.txt"
    if command -v rclone &>/dev/null && rclone listremotes 2>/dev/null | grep -q '^a-gdrive2:'; then
        _DEV=$(cat "$D/adata/local/.device" 2>/dev/null || hostname)
        _BDIR="$D/adata/backup/$_DEV"; mkdir -p "$_BDIR"
        if [[ ! -f "$_BDIR/.gdrive_id" ]]; then
            rclone mkdir "a-gdrive2:/$_DEV" 2>/dev/null
            _GID=$(rclone lsjson a-gdrive2:/ --dirs-only 2>/dev/null | python3 -c "import sys,json;[print(x['ID']) for x in json.load(sys.stdin) if x['Name']=='$_DEV']" 2>/dev/null)
            [[ -n "$_GID" ]] && { echo "$_GID" > "$_BDIR/.gdrive_id"; ok "gdrive folder: $_DEV"; } || warn "gdrive folder setup failed"
        else ok "gdrive folder: $_DEV"; fi
    fi
    RC="$HOME/.bashrc"; [[ -n "$ZSH_VERSION" ]] && RC="$HOME/.zshrc"
    source "$RC" 2>/dev/null && ok "shell ready" || warn "run: source $RC"
    echo -e "\n${G}✓${R} Install complete — type ${G}a${R}\n"
    ;;
dmg) T=$(mktemp -d);N="Install a";mkdir -p "$T/$N.app/Contents/MacOS";printf '<plist><dict><key>CFBundleExecutable</key><string>a</string><key>CFBundleName</key><string>Install a</string></dict></plist>'>"$T/$N.app/Contents/Info.plist";printf '#!/bin/sh\nosascript -e '\''tell application "Terminal" to do script "curl -fsSL https://raw.githubusercontent.com/seanpattencode/a/main/a.c -o /tmp/a-install && sh /tmp/a-install"'\''&\n'>"$T/$N.app/Contents/MacOS/a";chmod +x "$T/$N.app/Contents/MacOS/a";printf 'If "Install a" is blocked by macOS:\n\nOpen Terminal (Cmd+Space, type Terminal) and paste:\n\ncurl -fsSL https://raw.githubusercontent.com/seanpattencode/a/main/a.c -o /tmp/a-install && sh /tmp/a-install\n'>"$T/README.txt";hdiutil create -volname "Install a" -srcfolder "$T" -ov -format UDZO "$D/a.dmg"&&ok "a.dmg";rm -rf "$T";;
deb) T=$(mktemp -d);mkdir "$T/DEBIAN";printf 'Package: a\nVersion: 1.0\nArchitecture: all\nMaintainer: seanpatten\nDescription: a\n'>"$T/DEBIAN/control";printf '#!/bin/sh\ncurl -fsSL https://raw.githubusercontent.com/seanpattencode/a/main/a.c|sh\n'>"$T/DEBIAN/postinst";chmod +x "$T/DEBIAN/postinst";dpkg-deb -b "$T" "$D/a.deb"&&ok "a.deb";rm -rf "$T";;
*)
    echo "Usage: sh a.c [build|install|analyze|shell|clean|dmg|deb]"
    ;;
esac
exit 0
#endif
/* a.c — self-compiling agent manager. sh a.c && a <args> to test. */
#ifndef __APPLE__
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <dirent.h>
#include <time.h>
#include <fcntl.h>
#include <arpa/inet.h>
#include <signal.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <ctype.h>
#include <limits.h>
#include <poll.h>
#ifdef __linux__
#include <sys/inotify.h>
#endif
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

#define P 1024
#define B 4096
#define MP 256
#define MA 64
#define MS 48
#define AB if(getenv("A_BENCH"))return 0
#define CWD(w) char w[P];if(!getcwd(w,P))snprintf(w,P,"%s",HOME)

/* a.c: cmd_freq,cmd_cat,cmd_j,cmd_tmux,cmd_tutorial,CMDS[],perf,main */
static void mkdirp(const char *p);
static void alog(const char *cmd, const char *cwd);
static void perf_disarm(void);
static int cmd_sess(int, char**);
static char *cfget(const char *key);
typedef struct{char n[64];int c;}FC;
static int ctcmp(const void*a,const void*b){return((const FC*)b)->c-((const FC*)a)->c;}
static const char*EXT[]={"",".py",".c",".sh",".html",0};

#include "lib/globals.c"
#include "lib/init.c"
#include "lib/util.c"
#include "lib/kv.c"
#include "lib/data.c"
#include "lib/tmux.c"
#include "lib/git.c"
#include "lib/fork.c"
#include "lib/session.c"
#include "lib/alog.c"
#include "lib/help.c"
#include "lib/project.c"
#include "lib/config.c"
#include "lib/push.c"
#include "lib/hub.c"
#include "lib/ls.c"
#include "lib/note.c"
#include "lib/book.c"
#include "lib/ssh.c"
#include "lib/scp.c"
#include "lib/net.c"
#include "lib/agent.c"
#include "lib/file.c"
#include "lib/cc.c"
#include "lib/cmd.c"
#include "lib/perf.c"
#include "lib/work.c"
#include "lib/sess.c"
#include "lib/vm.c"
#include "lib/new.c"
#include "lib/op.c"
#include "lib/pow.c"
#include "lib/serve.c"
#include "lib/tok.c"
#include "lib/m.c"
#include "lib/h.c"
#include "lib/handoff.c"
#include "lib/pedal.c"
#include "lib/grep.c"
#include "lib/fleet.c"

static int cmd_freq(int c,char**v){perf_disarm();
    int vb=0,n=0;
    for(int i=2;i<c;i++){if(!strcmp(v[i],"-v"))vb=1;else if(*v[i]>='0'&&*v[i]<='9')n=atoi(v[i]);}
    char ad[P];snprintf(ad,P,"%s/local/activity",AROOT);
    char fc[P+64];snprintf(fc,sizeof(fc),"find '%s' -maxdepth 2 -name '*_*.txt' 2>/dev/null",ad);
    FILE*d=popen(fc,"r");if(!d){puts("x no activity log");return 1;}
    FC ct[1024]={0};int nc=0;
    char fp[P],ln[256];
    while(fgets(fp,P,d)){fp[strcspn(fp,"\n")]=0;
        FILE*af=fopen(fp,"r");if(!af)continue;
        while(fgets(ln,256,af)){
        char*p=ln;for(int i=0;i<3&&*p;i++){while(*p&&*p!=' ')p++;while(*p==' ')p++;}
        char*end=p;while(*end&&*end!='\n')end++;*end=0;
        if(!*p)continue;
        end=p;while(*end&&*end!=' ')end++;
        if(vb&&*end){end++;while(*end&&*end!=' '&&*end!='\n')end++;}
        *end=0;
        int j;for(j=0;j<nc;j++)if(!strcmp(ct[j].n,p)){ct[j].c++;break;}
        if(j==nc&&nc<1024){snprintf(ct[nc].n,64,"%s",p);ct[nc].c=1;nc++;}}
        fclose(af);}
    pclose(d);
    qsort(ct,(size_t)nc,sizeof(ct[0]),ctcmp);
    if(!n||n>nc)n=nc;
    long tu=0,tk=0;
    printf("%6s %5s %5s %s\n","USES","FILE","USE/K","CMD");
    for(int i=0;i<n;i++){struct stat st;char sf[P];long kb=0;
        const char*cn=ct[i].n;static const char*AL[]={"t","task","n","note","i","ls","diff","push","d","push","kill","ls","j","sess","jobs","sess",0};
        for(int a=0;AL[a];a+=2)if(!strcmp(cn,AL[a])){cn=AL[a+1];break;}
        static const char*X[]={".c",".py",NULL};
        for(int x=0;X[x];x++){snprintf(sf,P,"%s/lib/%s%s",SDIR,cn,X[x]);if(!stat(sf,&st)){kb=(st.st_size+512)/1024;break;}}
        tu+=ct[i].c;if(kb)tk+=kb;
        if(kb)printf("%6d %4ldK %5ld %s\n",ct[i].c,kb,ct[i].c/kb,ct[i].n);
        else printf("%6d             %s\n",ct[i].c,ct[i].n);}
    if(tk)printf("\n%ld uses, %ldK code, %ld u/K overall\n",tu,tk,tk?tu/tk:0);
    puts("\033[33m! includes bot/auto use\033[0m");
    return 0;}
static int cmd_cat(int c,char**v){perf_disarm();  /* a cat [1|3] [dir]: newest files first, whole under A_CB bytes (default 1.2MB), 10+5-line stubs past it; the digit is ignored (old callers) */
    int di=2;if(c>2&&v[2][0]>='1'&&v[2][0]<='3'&&!v[2][1])di=3;
    if(c>di&&chdir(v[di]))return 1;
    #define GA(p,n) if(l+(n)>=cap){cap=(l+(n)+8192)*2;d=realloc(d,cap);}memcpy(d+l,p,n);l+=(n)
    {char cm[B];init_db();load_cfg();CWD(wc);size_t sl=strlen(SDIR);
    int ia=!strcmp(cfget("cat_a"),"on")&&(strncmp(wc,SDIR,sl)||(wc[sl]&&wc[sl]!='/'));
    snprintf(cm,B,"A='%s';{ git grep -lI '';for d in %s;do git -C \"$d\" grep -lI ''|sed \"s|^|$d/|\";done;%s } 2>/dev/null|tr '\\n' '\\0'|xargs -0 ls -t 2>/dev/null",SDIR,cfget("cat_more"),ia?"git -C \"$A\" grep -lI ''|sed \"s|^|$A/|\";":"");  /* cwd repo + cat_more repos (u) + /a (stubs when outside it), newest first so the budget goes to live files */
    size_t l=0,cap=0;char*d=NULL,b[8192];size_t n;int nf=0,nst=0,nam=0;
    size_t bud=getenv("A_CB")?(size_t)atol(getenv("A_CB")):1200000;
    FILE*fl=popen(cm,"r");char fb[65536];size_t fl2=0;
    if(fl){while((n=fread(b,1,8192,fl))>0){if(fl2+n<65536){memcpy(fb+fl2,b,n);fl2+=n;}}pclose(fl);}
    fb[fl2]=0;
    if(ia){const char*am="\nYou are an agent spawned by the a agent manager. The source code is included for better understnading of the tools you can use. If you encounter issues in their use, consider fixing them and sending a pr of the fix as shorter tokens.\n";GA(am,strlen(am));}
    for(char*p=fb;p<fb+fl2&&l<6*1024*1024;){char*e=memchr(p,'\n',(size_t)(fb+fl2-p));if(!e)break;*e=0;
        FILE*f=fopen(p,"r");if(!f){p=e+1;continue;}
        int tl=0;char ln[512];while(fgets(ln,512,f))tl++;
        rewind(f);nf++;
        char hdr[600];size_t hl=(size_t)snprintf(hdr,600,"\n==> %s (%d lines) <==\n",p,tl);
        GA(hdr,hl);
        int am=ia&&!strncmp(p,SDIR,sl)&&p[sl]=='/',st=l>bud||am;nam+=st&&am;nst+=st&&!am;int hd=st?10:tl,tl2=5;
        int i=0;while(fgets(ln,512,f)){size_t ll=strlen(ln);
            if(i<hd||(tl>hd+tl2&&i>=tl-tl2)){GA(ln,ll);}
            if(i==hd&&tl>hd+tl2){GA("  ...\n",6);}
            i++;}
        fclose(f);p=e+1;}
    CWD(cd);const char*actx=getenv("A_CTX");char ctd[P];
    if(actx&&actx[0]=='/')snprintf(ctd,P,"%s",actx);else snprintf(ctd,P,"%s/context/%s",AROOT,actx&&actx[0]?actx:bname(cd));
    #define CTX_EMIT(FP,HDR) {FILE*cf=fopen(FP,"r");if(cf){size_t sr=fread(b,1,512,cf);int bin=l>bud;  /* bud gates context too — 2.4MB embed blew the 1M window */\
        for(size_t i=0;i<sr&&!bin;i++)if((unsigned char)b[i]<32&&b[i]!=9&&b[i]!=10&&b[i]!=13)bin=1;\
        {size_t hl=(size_t)snprintf(b,8192,"\n==> context%s: %s <==\n",bin?" doc":"",bin?FP:HDR);GA(b,hl);}\
        if(bin)fclose(cf);else{rewind(cf);while(fgets(b,512,cf)){size_t bl=strlen(b);GA(b,bl);}fclose(cf);}nf++;}}
    struct stat _cs;
    if(!stat(ctd,&_cs)&&S_ISREG(_cs.st_mode))CTX_EMIT(ctd,bname(ctd))
    else {DIR*dd=opendir(ctd);if(dd){struct dirent*de;while((de=readdir(dd))){if(de->d_name[0]=='.')continue;
        char fp2[P];snprintf(fp2,P,"%s/%s",ctd,de->d_name);
        struct stat st2;if(!stat(fp2,&st2)&&S_ISDIR(st2.st_mode)){DIR*sd=opendir(fp2);if(sd){struct dirent*se;while((se=readdir(sd))){if(se->d_name[0]=='.')continue;
            char sp[P],sh[260];snprintf(sp,P,"%s/%s",fp2,se->d_name);snprintf(sh,260,"%s/%s",de->d_name,se->d_name);CTX_EMIT(sp,sh)}closedir(sd);}continue;}
        CTX_EMIT(fp2,de->d_name)}closedir(dd);}}
    #undef CTX_EMIT
    size_t cl2=l;
    if(!getenv("A_NOPROMPT")){const char*ap=cfget("prompt");if(!*ap)ap="default";char p[P];snprintf(p,P,"%s/common/prompts/%s.txt",SROOT,ap);FILE*f=fopen(p,"r");
     if(f){char hd[64];size_t hl2=(size_t)snprintf(hd,64,"\n==> prompt: %s <==\n",ap);GA(hd,hl2);char pb[512];size_t r;while((r=fread(pb,1,512,f))>0){GA(pb,r);}fclose(f);nf++;}}
    if(!d)return 1;d[l]=0;
    char tf[P];snprintf(tf,P,"%s/local/a_cat.txt",AROOT);writef(tf,d);
    {int lc=0;for(size_t i=0;i<l;i++)if(d[i]=='\n')lc++;dprintf(1,"Read %s (%d lines) in full. CONTEXT %s: %d files, %d /a as map (10+5 lines), %d stubbed (A_CB=%zu)\n\n",tf,lc,nst?"INCOMPLETE":"COMPLETE",nf,nam,nst,bud);}
    (void)!write(1,d,l);to_clip(d);
    fprintf(stderr,"✓ %d files %zu+%zuprompt tok cat %s\n  context: %s/\n",nf,cl2/4,(l-cl2)/4,tf,ctd);
    free(d);}
    #undef GA
    return 0;}
static int cmd_j(int c,char**v){
    if(c<3||!strcmp(v[2],"rm")||!strcmp(v[2],"watch")||!strcmp(v[2],"-r")||(c==3&&isdigit(*v[2])))return cmd_jobs(c,v);
    if(c>2&&!strcmp(v[2],"-q")){perf_disarm();char ln[B],ob[4096];  /* rapid entry: each line spawns a detached claude win, stays in loop */
        for(fputs("j> ",stdout),fflush(stdout);fgets(ln,B,stdin);fputs("j> ",stdout),fflush(stdout)){
            ln[strcspn(ln,"\n")]=0;if(!*ln)continue;int p[2];if(pipe(p))continue;
            if(!fork()){dup2(p[1],1);dup2(p[1],2);close(p[0]);execlp("a","a","j",ln,(char*)0);_exit(127);}
            close(p[1]);int t=0,r;while(t<4095&&(r=(int)read(p[0],ob+t,(size_t)(4095-t)))>0)t+=r;ob[t]=0;
            close(p[0]);wait(0);char*w=strstr(ob,"→ tmux win");if(w){char*e=strchr(w,'\n');if(e)*e=0;}puts(w?w:"+ sent");}
        return 0;}
    if(c==3&&!strcmp(v[2],"a")){if(!getenv("TMUX")){puts("x Needs tmux");return 1;}
        char cf[P],pr[B],cm[B],pid[64];snprintf(cf,P,"%s/job_context.txt",DDIR);
        {char nd[P];FILE*f=fopen(cf,"w");if(f){
            snprintf(nd,P,"%s/notes",SROOT);int nn=load_notes(nd,NULL);
            for(int i=0;i<nn;i++)fprintf(f,"%d. %s\n",i+1,gn[i].t);
            fputs("\n",f);snprintf(nd,P,"%s/tasks.txt",SROOT);char*tt=readf(nd,NULL);int k=0;   /* task board headers (lib/task.py) */
            for(char*l=tt;l&&*l;){int L=(int)strcspn(l,"\n");if(!strncmp(l,"== ",3))fprintf(f,"%d. %.*s\n",++k,L,l);l+=L+(l[L]=='\n');}
            free(tt);fclose(f);}}
        snprintf(pr,B,"%s/common/prompts/job.txt",SROOT);
        char*ap=readf(pr,NULL);snprintf(pr,B,"%s\nContext: cat %s",ap?ap:"Ask what to work on. cat a.c for source.",cf);if(ap)free(ap);
        {char ctxf[P];snprintf(ctxf,P,"%s/a_ctx_%d.txt",TMP,(int)getpid());
        write_prompt_file(ctxf,SDIR,pr);
        snprintf(cm,B,"tmux split-window -fhP -F '#{pane_id}' -c '%s' '" ACAT " >>%s 2>/dev/null;claude --dangerously-skip-permissions --model claude-fable-5 --effort max --append-system-prompt-file %s'",SDIR,ctxf,ctxf);
        pcmd(cm,pid,64);}return 0;}
    {char nb[16]="";pcmd("pgrep -xc claude 2>/dev/null||echo 0",nb,16);
    int nj=atoi(nb)-1;if(nj<0)nj=0;
    if(nj>=100&&!(c>2&&!strcmp(v[2],"--resume"))){printf("x %d/100 slots full, see: a j\n",nj);return 1;}}
    init_db();load_cfg();load_proj();CWD(wd);
    if(c>3&&!strcmp(v[2],"--resume")){snprintf(wd,P,"%s",v[3]);
        if(!dexists(wd)){printf("x %s not found\n",wd);return 1;}
        printf("+ resume: %s\n",wd);
        tm_ensure_conf();char jcmd[B];jcmd_fill(jcmd,1,wd,NULL);
        {char sn[64];snprintf(sn,64,"j-%s",bname(wd));if(!tm_new(sn,wd,jcmd))sess_log(sn,wd);tm_go(sn);}
        return 0;}
    int si=2,wt=0;if(c>3&&isdigit(*v[2])){int idx=atoi(v[2]);if(idx<NPJ)snprintf(wd,P,"%s",PJ[idx].path);si++;}
    /* jobs run on main by default. --wt opts into fork isolation. agents work in parallel, push only their files. */
    char pr[B]="";int pl=0;for(int i=si;i<c;i++){if(!strcmp(v[i],"--wt")){wt=1;continue;}if(!strcmp(v[i],"--no-wt"))continue;pl+=snprintf(pr+pl,(size_t)(B-pl),"%s%s",pl?" ":"",v[i]);}
    {struct stat pf;const char*dt=strrchr(pr,'.');   /* whole prompt = existing .txt/.md path → load file as the prompt */
     if(dt&&(!strcmp(dt,".txt")||!strcmp(dt,".md"))&&!stat(pr,&pf)&&S_ISREG(pf.st_mode)){char*fc=readf(pr,NULL);if(fc){
        if(strlen(fc)>(size_t)B-200){printf("x %s: >%d bytes, too big for j\n",pr,B-200);free(fc);return 1;}
        printf("+ prompt ← %s\n",pr);pl=snprintf(pr,B,"%s",fc);free(fc);}}}
    if(wt&&git_in_repo(wd)){
        char fkd[P];snprintf(fkd,P,"%s/forks",AROOT);mkdirp(fkd);
        time_t now=time(NULL);struct tm*t=localtime(&now);char ts[16];
        strftime(ts,16,"%b%d",t);for(char*p=ts;*p;p++)*p=(char)tolower(*p);
        int h=t->tm_hour%12;if(!h)h=12;char nm[64],fp[P];
        snprintf(nm,64,"%s-%s-%d%02d%02d%s",bname(wd),ts,h,t->tm_min,t->tm_sec,t->tm_hour>=12?"pm":"am");
        snprintf(fp,P,"%s/%s",fkd,nm);
        if(!fork_cp(wd,fp)){printf("+ %s\n",fp);snprintf(wd,P,"%s",fp);}
    }
    printf("+ job: %s\n  %.*s\n",bname(wd),80,pr);
    if(pr[0])pl+=snprintf(pr+pl,(size_t)(B-pl),"\n\nWhen done: write .a_done — one simple sentence + test cmd; output beginning...end 4 lines max; no spacing between sections");
    tm_ensure_conf();
    char jcmd[B];jcmd_fill(jcmd,0,wd,pr[0]?pr:NULL);
    const char*sn=tm_name("j",bname(wd),time(0));
    if(!tm_new(sn,wd,jcmd))sess_log(sn,wd);
    {char q[160],wi[16]="?";snprintf(q,160,"tmux list-windows -t '" TMS "' -f '#{==:#{window_name},%s}' -F '#{window_index}' 2>/dev/null",sn);pcmd(q,wi,16);wi[strcspn(wi,"\n")]=0;printf("→ tmux win %s · %s\n",wi[0]?wi:"?",sn);}
    fflush(stdout);  /* tm_go execs without flushing stdio — emit the report first */
    if(isatty(1))tm_go(sn);  /* only switch to it when interactive; web/piped dispatch just creates + reports */
    return 0;}
static int cmd_tmux(int c,char**v){if(!getenv("TMUX")){tm_go(c>2?v[2]:NULL);return 0;}if(c>2){execvp("tmux",v+1);return 1;}setenv("A_FILT_TAG","win pane quit",1);return cmd_i(c,v);}
static int cmd_tutorial(int c,char**v){(void)c;
    char*fv[]={v[0],"a","Guide 'a'. Use 'a help'+README.md, teach as needed. scream=most essential.",NULL};
    return cmd_a_default(3,fv);}
static int run_lab(char*pf,char**argv){
    const char*dx=strrchr(pf,'.');perf_disarm();if(!dx)return -1;
    char*x=NULL;if(!strcmp(dx,".py"))x="python3";else if(!strcmp(dx,".sh"))x="sh";
    if(x){argv[1]=pf;argv[0]=x;execvp(x,argv);}
    if(!strcmp(dx,".c")){static char ob[P];char cm[B];const char*bn=bname(pf);
     snprintf(ob,P,"%s/lab_%.*s",TMP,(int)(dx-bn),bn);
     snprintf(cm,B,"cc -w -o '%s' '%s'",ob,pf);if(system(cm))return 1;argv[1]=ob;return execv(ob,argv+1);}
    if(!strcmp(dx,".html"))execlp("xdg-open","xdg-open",pf,(char*)0);
    return -1;}
typedef struct { const char *n; int (*fn)(int, char**); } cmd_t;
static int cmd_cmp(const void*a,const void*b){return strcmp(((const cmd_t*)a)->n,((const cmd_t*)b)->n);}
static const cmd_t CMDS[] = {
    {"--help",cmd_help_full},{"-h",cmd_help_full},
    {"a",cmd_a_default},{"add",cmd_add},{"agent",cmd_agent},
    {"book",cmd_book},{"cat",cmd_cat},{"cc",cmd_cc},{"clone",cmd_new},{"cmd",cmd_cmd},{"config",cmd_config},
    {"copy",cmd_copy},{"create",cmd_create},
    {"d",cmd_diff},{"diff",cmd_diff},{"dir",cmd_dir},{"docs",cmd_docs},{"done",cmd_done},
    {"e",cmd_e},{"email",cmd_email},{"file",cmd_get},{"fl",cmd_fl},{"fleet",cmd_fleet},{"fork",cmd_fork},{"freq",cmd_freq},{"grep",cmd_grep},{"h",cmd_h},{"handoff",cmd_handoff},
    {"help",cmd_help_full},{"home",cmd_h},{"hub",cmd_hub},{"i",cmd_i},
    {"install",cmd_install},{"j",cmd_j},
    {"kill",cmd_kill},{"log",cmd_log},{"login",cmd_login},{"ls",cmd_ls},
    {"m",cmd_m},{"mono",cmd_cat},{"monolith",cmd_cat},{"move",cmd_move},
    {"n",cmd_note},{"new",cmd_new},{"note",cmd_note},
    {"o",cmd_op},{"op",cmd_op},{"operator",cmd_op},
    {"p",cmd_push},{"pedal",cmd_pedal},{"perf",cmd_perf},{"pow",cmd_pow},{"pr",cmd_pr},{"prompt",cmd_prompt},
    {"pull",cmd_pull},{"push",cmd_push},
    {"remove",cmd_remove},{"repo",cmd_create},{"resume",cmd_resume},{"revert",cmd_revert},{"review",cmd_review},
    {"rm",cmd_remove},{"scan",cmd_scan},{"scp",cmd_scp},{"search",cmd_search},{"serve",cmd_serve},
    {"settings",cmd_settings},{"setup",cmd_setup},{"snap",cmd_resume},
    {"ssh",cmd_ssh},{"sw",cmd_swarm},
    {"sync",cmd_sync},{"t",cmd_task},{"task",cmd_task},
    {"tmux",cmd_tmux},{"tok",cmd_tok},{"tutorial",cmd_tutorial},{"u",cmd_update},
    {"uninstall",cmd_uninstall},{"update",cmd_update},
    {"vm",cmd_vm},
    {"w",cmd_w},{"work",cmd_w},
    {"x",cmd_x},
};
#define NCMDS (sizeof(CMDS)/sizeof(*CMDS))
static char perf_msg[B];
__attribute__((noreturn)) static void perf_alarm(int sig){(void)sig;
    (void)!write(STDERR_FILENO,perf_msg,strlen(perf_msg));kill(-getpid(),SIGTERM);_exit(124);}  /* pgrp 0 from tmux run-shell = server */
static void perf_arm(const char *cmd) {
    if(getenv("A_BENCH")||isdigit(*cmd))return;
    char sk[64];snprintf(sk,64,"|%s|",cmd);
    if(strstr("|push|pull|sync|u|update|login|ssh|sw|gdrive|email|install|j|job|pr|hub|create|repo|move|e|revert|diff|d|perf|pow|scan|review|fork|kill|ls|i|deps|log|serve|c|l|g|co|cp|gp|done|clone|add|cmd|",sk))return;
    unsigned l=1000000;char pf[P];snprintf(pf,P,"%s/perf/%s.txt",SROOT,DEV);
    {char*d=readf(pf,NULL);unsigned pl=perf_limit(d,cmd);if(pl>=500)l=pl;free(d);}
    snprintf(perf_msg,B,"\n\033[31m✗ PERF KILL\033[0m: 'a %s' >%.1fms (%s)\n  %s\n",cmd,l/1000.0,DEV,pf);
    signal(SIGALRM,perf_alarm);
    struct itimerval tv={{0,0},{(long)(l/1000000),(long)(l%1000000)}};setitimer(ITIMER_REAL,&tv,NULL);
}
static void perf_disarm(void) { alarm(0);signal(SIGALRM,SIG_DFL); }
static struct timespec gt0;
static void gt_print(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
    fprintf(stderr,"%ldus\n",(t.tv_sec-gt0.tv_sec)*1000000L+(t.tv_nsec-gt0.tv_nsec)/1000);}
int main(int argc, char **argv) {
    clock_gettime(CLOCK_MONOTONIC, &T0);
    signal(SIGCHLD,SIG_DFL);  /* serve execs us with SIGCHLD=IGN: system() rc=-1 → phantom snap restores */
    init_paths();

    clock_gettime(CLOCK_MONOTONIC,&gt0);atexit(gt_print);
    if(!strcmp(bname(argv[0]),"h"))return cmd_h(argc,argv);  /* multicall: `h` symlink = one-keypress home */
    if (argc < 2) { if(isatty(1))ifr_blast(); perf_arm("i"); return (isatty(1)?cmd_i:cmd_help)(argc, argv); }  /* blast cached frame pre-init; cmd_i repaints over it */
    char acmd[B]="";ajoin(acmd,B,argc,argv,1);
    CWD(wd);
    alog(acmd, wd);
    const char *arg = argv[1];
    /* per-cmd auto-sync removed: was sweeping working-tree changes (e.g. my/ lab work) into "sync" commits across adata. Notes/tasks still sync on their explicit write paths. */

    if (*arg && !arg[strspn(arg,"0123456789")]) { init_db(); return cmd_project_num(argc, argv, atoi(arg)); }

    perf_arm(arg);

    { cmd_t key = {arg, NULL};
      const cmd_t *c = bsearch(&key, CMDS, NCMDS, sizeof(*CMDS), cmd_cmp);
      if (c) return c->fn(argc, argv); }

    {char pf[P];snprintf(pf,P,"%s/lib/%s.py",SDIR,arg);
     if(fexists(pf))fallback_py(arg,argc,argv);
     snprintf(pf,P,"%s/lib/%s/__init__.py",SDIR,arg);
     if(fexists(pf)){char m[P];snprintf(m,P,"%s/__init__",arg);fallback_py(m,argc,argv);}
     #define RL {int r=run_lab(pf,argv);if(r>=0)return r;}
     for(int i=2;EXT[i];i++){snprintf(pf,P,"%s/lib/%s%s",SDIR,arg,EXT[i]);if(fexists(pf))RL}
     snprintf(pf,P,"%s/my/%s",SDIR,arg);
     if(strrchr(arg,'.')&&fexists(pf))RL
     for(int i=1;EXT[i];i++){snprintf(pf,P,"%s/my/%s%s",SDIR,arg,EXT[i]);if(fexists(pf))RL}
     init_db();load_cfg();load_sess();if(find_sess(arg))return cmd_sess(argc,argv);
     DIR*ld;struct dirent*le;snprintf(pf,P,"%s/my",SROOT);ld=opendir(pf);
     if(ld){while((le=readdir(ld))){if(le->d_name[0]=='.')continue;
      for(int i=1;EXT[i];i++){snprintf(pf,P,"%s/my/%s/%s%s",SROOT,le->d_name,arg,EXT[i]);
       if(fexists(pf)){closedir(ld);RL}}}closedir(ld);}
     #undef RL
     }
    if(dexists(arg)||fexists(arg))return cmd_dir_file(argc,argv);
    {char ep[P];snprintf(ep,P,"%s%s",HOME,arg);if(*arg=='/'&&dexists(ep))return cmd_dir_file(argc,argv);}
    if(strlen(arg)<=3&&islower(*arg))return cmd_sess(argc,argv);
    if(tm_has(arg)){tm_go(arg);return 0;}
    {char mf[P];
     for(int i=0;EXT[i];i++){snprintf(mf,P,"%s/my/%s%s",SROOT,arg,EXT[i]);
      if(fexists(mf)){char md[P];snprintf(md,P,"%s/my",SROOT);(void)!chdir(md);return run_lab(mf,argv);}}}
    fprintf(stderr,"a: unknown '%s'\n",arg);
    return 1;
}
