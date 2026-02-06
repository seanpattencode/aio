#!/bin/bash
# Install ac: C binary + 0ms bash wrapper
# Fast paths (help, number, dir) use pure bash builtins = 0ms
# Everything else uses C binary (~18ms on Termux vs 200ms Python)
set -e

G='\033[32m' R='\033[0m'
ok() { echo -e "${G}✓${R} $1"; }

BIN="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AC_SRC="$SCRIPT_DIR/../ac.c"
[[ -f "$AC_SRC" ]] || AC_SRC="$SCRIPT_DIR/ac.c"
mkdir -p "$BIN"

# Compile
if [[ -f "$AC_SRC" ]]; then
    gcc -O2 -Wall -Wextra -Wno-unused-parameter \
        -I"$HOME/micromamba/include" -L"$HOME/micromamba/lib" \
        -o "$BIN/ac" "$AC_SRC" -lsqlite3
    ok "ac compiled ($(wc -c < "$BIN/ac") bytes)"
else
    echo "✗ $AC_SRC not found"; exit 1
fi

# Install bash function: pure builtins for fast paths, ac binary for rest
for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [[ -f "$RC" ]] || continue
    # Remove old function
    sed -i -e '/^a() {/,/^}/d' -e '/^aio() {/d' -e '/^ai() {/d' "$RC" 2>/dev/null||:
    cat >> "$RC" << 'AFUNC'
a() {
    local cache=~/.local/share/a/help_cache.txt projects=~/.local/share/a/projects.txt
    # No args: print cached help (builtin read, 0ms)
    if [[ -z "$1" ]]; then
        [[ -f "$cache" ]] && printf '%s\n' "$(<"$cache")" || command ac
        return
    fi
    # Number: cd to project (builtin mapfile, 0ms)
    if [[ "$1" =~ ^[0-9]+$ ]]; then
        local -a lines; mapfile -t lines < "$projects" 2>/dev/null
        local dir="${lines[$1]}"
        if [[ -n "$dir" && -d "$dir" ]]; then printf '📂 %s\n' "$dir"; cd "$dir"; return; fi
    fi
    # Directory: cd into it (0ms)
    local d="${1/#\~/$HOME}"; [[ "$1" == /projects/* ]] && d="$HOME$1"
    [[ -d "$d" ]] && { printf '📂 %s\n' "$d"; cd "$d"; return; }
    # Everything else: C binary
    command ac "$@"
}
aio() { a "$@"; }
ai() { a "$@"; }
AFUNC
    ok "shell function → $RC"
done

# Source into current shell
source "$HOME/.bashrc" 2>/dev/null || source "$HOME/.zshrc" 2>/dev/null || true

# Verify
echo ""
echo "ac (C binary):"
time "$BIN/ac" >/dev/null 2>&1
echo ""
echo "a (bash builtin):"
time a >/dev/null 2>&1
echo ""
ok "done — ac installed, bash function loaded"
