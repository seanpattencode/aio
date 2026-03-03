#!/bin/bash
# Test script for pipe-pane activity monitoring
# Tests that title shows green during output, red after 5s silence

set -e
SESSION="test-pipe-monitor-$$"
PASS=0
FAIL=0

cleanup() {
    tmux kill-session -t "$SESSION" 2>/dev/null || true
}
trap cleanup EXIT

log() { echo "[$(date +%H:%M:%S)] $*"; }
pass() { log "PASS: $1"; PASS=$((PASS+1)); }
fail() { log "FAIL: $1"; FAIL=$((FAIL+1)); }

get_title() {
    tmux show-options -t "$SESSION" -v set-titles-string 2>/dev/null || echo "(none)"
}

# Create test session with a simple command that we control
log "Creating test session: $SESSION"
tmux new-session -d -s "$SESSION" -x 80 -y 24 "bash"
sleep 0.5

# Set up pipe-pane monitor (same as aio.py does)
log "Setting up pipe-pane monitor..."
tmux pipe-pane -t "$SESSION" -o "bash -c 's=$SESSION;tmux set -t \$s set-titles-string \"🔴 #S:#W\";while true;do if IFS= read -t5 l;then tmux set -t \$s set-titles-string \"🟢 #S:#W\";elif [[ \$? -gt 128 ]];then tmux set -t \$s set-titles-string \"🔴 #S:#W\";else exit;fi;done'"
sleep 0.3

# Test 1: Initial state should be red (no output yet)
title=$(get_title)
log "Test 1: Initial title = '$title'"
if [[ "$title" == *"🔴"* ]]; then
    pass "Initial state is red"
else
    fail "Initial state should be red, got: $title"
fi

# Test 2: Send output, should turn green
log "Test 2: Sending output..."
tmux send-keys -t "$SESSION" "echo 'Hello World'" Enter
sleep 0.5
title=$(get_title)
log "After output, title = '$title'"
if [[ "$title" == *"🟢"* ]]; then
    pass "Title turns green on output"
else
    fail "Title should be green after output, got: $title"
fi

# Test 3: Keep sending output, should stay green
log "Test 3: Continuous output..."
tmux send-keys -t "$SESSION" "for i in 1 2 3; do echo \$i; sleep 1; done" Enter
sleep 2
title=$(get_title)
log "During continuous output, title = '$title'"
if [[ "$title" == *"🟢"* ]]; then
    pass "Title stays green during continuous output"
else
    fail "Title should stay green during output, got: $title"
fi

# Test 4: Wait for silence timeout (5s), should turn red
log "Test 4: Waiting 7s for silence timeout..."
sleep 7
title=$(get_title)
log "After 7s silence, title = '$title'"
if [[ "$title" == *"🔴"* ]]; then
    pass "Title turns red after silence"
else
    fail "Title should be red after 5s silence, got: $title"
fi

# Test 5: Output again, should turn green again
log "Test 5: Output after silence..."
tmux send-keys -t "$SESSION" "echo 'Back again'" Enter
sleep 0.5
title=$(get_title)
log "After new output, title = '$title'"
if [[ "$title" == *"🟢"* ]]; then
    pass "Title turns green again after new output"
else
    fail "Title should be green after new output, got: $title"
fi

# Test 6: Verify expected process count (sh wrapper + bash = 2 processes per pipe-pane)
log "Test 6: Checking process count..."
procs=$(pgrep -f "tmux set -t.*$SESSION" 2>/dev/null | wc -l)
log "Found $procs pipe-pane processes (expected: 2 = sh wrapper + bash)"
if [[ "$procs" -eq 2 ]]; then
    pass "Correct process count (2)"
else
    fail "Expected 2 processes, found: $procs"
fi

# Test 7: Verify processes are cleaned up when session is killed
log "Test 7: Killing session and checking cleanup..."
tmux kill-session -t "$SESSION" 2>/dev/null
trap - EXIT  # Disable cleanup trap since we already killed
sleep 0.5
remaining=$(pgrep -f "tmux set -t.*$SESSION" 2>/dev/null | wc -l)
log "After kill, found $remaining processes (expected: 0)"
if [[ "$remaining" -eq 0 ]]; then
    pass "Processes cleaned up after session kill"
else
    fail "Found $remaining orphaned processes after session kill"
fi

# Summary
echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
echo "================================"

if [[ "$FAIL" -eq 0 ]]; then
    echo "All tests passed!"
    exit 0
else
    echo "Some tests failed!"
    exit 1
fi
