#!/bin/bash
# test_copy.sh — verify a copy actually puts content on clipboard
# Uses powershell.exe Get-Clipboard on WSL, pbpaste on mac, xclip -o on X11
set +e
D="$(cd "$(dirname "$0")/.." && pwd)"
A="$D/a"
PASS=0 FAIL=0

get_clip() {
    if [[ -x /mnt/c/Windows/System32/clip.exe ]]; then
        powershell.exe -NoProfile -Command "Get-Clipboard" 2>/dev/null | tr -d '\r'
    elif command -v pbpaste &>/dev/null; then pbpaste
    elif command -v wl-paste &>/dev/null; then wl-paste
    elif command -v xclip &>/dev/null; then xclip -selection clipboard -o
    else echo "NO_CLIP_READ"; return 1; fi
}
clear_clip() { echo -n "CLEARED" | clip.exe 2>/dev/null || echo -n "CLEARED" | xclip -sel c 2>/dev/null || :; }

check() {
    local label="$1" expect="$2" got="$3"
    expect="$(printf '%s' "$expect" | sed 's/[[:space:]]*$//')"
    got="$(printf '%s' "$got" | sed 's/[[:space:]]*$//')"
    if [[ "$got" == "$expect" ]]; then
        echo "  PASS: $label"; ((PASS++))
    else
        echo "  FAIL: $label"
        echo "    expect: $(echo "$expect" | head -1)"
        echo "    got:    $(echo "$got" | head -1)"
        ((FAIL++))
    fi
}

echo "=== a copy test suite ==="
echo "binary: $A"
echo "clip read: $(get_clip >/dev/null 2>&1 && echo ok || echo missing)"
echo

# --- Test 1: pipe simple string ---
echo "--- Test 1: pipe simple ---"
clear_clip
echo "hello_copy_test" | "$A" copy >/dev/null 2>&1
check "pipe simple" "hello_copy_test" "$(get_clip)"

# --- Test 2: pipe multiline ---
echo "--- Test 2: pipe multiline ---"
clear_clip
printf "line1\nline2\nline3" | "$A" copy >/dev/null 2>&1
check "pipe multiline" "line1
line2
line3" "$(get_clip)"

# --- Test 3: pipe real command output ---
echo "--- Test 3: pipe command ---"
clear_clip
echo "real_output_42" | "$A" copy >/dev/null 2>&1
check "pipe cmd" "real_output_42" "$(get_clip)"

# --- Test 4: plain bash via shell function (re-run last cmd) ---
echo "--- Test 4: plain bash (shell function re-run) ---"
clear_clip
# Simulate interactive bash: source shell func, run a cmd, run a copy
# Use bash -i so fc/history works, feed commands via script for pty
RCFILE=$(mktemp)
cat > "$RCFILE" << RCEOF
set -o history
HISTFILE=/tmp/a_test_hist
_ADD="$D/adata/local"
a() {
    local dd="\$_ADD"
    [[ -z "\$1" ]] && return
    [[ "\$1" == "copy" && -z "\$TMUX" && -t 0 ]] && { local lc="\$(fc -ln -2 -2 2>/dev/null|sed 's/^\s*//')"; [[ -z "\$lc" || "\$lc" == a\ copy* ]] && { echo "x No previous command"; return 1; }; eval "\$lc" 2>&1 | command a copy; return; }
    command a "\$@"
}
RCEOF
# Use script to provide a pty, bash -i for history/fc
unset TMUX; script -qc "env -u TMUX bash --rcfile '$RCFILE' -i" /dev/null << 'CMDS'
echo "plain_bash_output_77"
a copy
exit
CMDS
rm -f "$RCFILE"
GOT="$(get_clip)"
check "plain bash rerun" "plain_bash_output_77" "$GOT"

# --- Test 5: empty pipe ---
echo "--- Test 5: empty pipe ---"
OUT="$(printf '' | "$A" copy 2>&1)"
check "empty pipe msg" "x No output" "$OUT"

echo
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] && echo "ALL PASS" || echo "NEEDS WORK"
exit $FAIL
