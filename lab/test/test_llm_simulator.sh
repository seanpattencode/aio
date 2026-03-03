#!/bin/bash
# Test pipe-pane monitoring with LLM CLI simulator
# Runs the simulator for 30s and verifies status transitions

set -e
SESSION="llm-sim-test-$$"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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

get_status() {
    local title=$(get_title)
    if [[ "$title" == *"🟢"* ]]; then
        echo "green"
    elif [[ "$title" == *"🔴"* ]]; then
        echo "red"
    else
        echo "unknown"
    fi
}

# Make simulator executable
chmod +x "$SCRIPT_DIR/llm_simulator.sh"

log "=========================================="
log "LLM Simulator Pipe-Pane Monitor Test"
log "=========================================="
echo ""

# Create test session running the simple simulator (10 second run)
log "Creating session with simple simulator (10s run)..."
tmux new-session -d -s "$SESSION" -x 80 -y 24 "$SCRIPT_DIR/simple_simulator.sh 10"
sleep 0.5

# Set up pipe-pane monitor (same as aio.py)
log "Setting up pipe-pane activity monitor..."
tmux pipe-pane -t "$SESSION" -o "bash -c 's=$SESSION;tmux set -t \$s set-titles-string \"🔴 #S:#W\";while true;do if IFS= read -t5 l;then tmux set -t \$s set-titles-string \"🟢 #S:#W\";elif [[ \$? -gt 128 ]];then tmux set -t \$s set-titles-string \"🔴 #S:#W\";else exit;fi;done'"
sleep 0.5

echo ""
log "Monitoring status changes over time..."
log "(Simulator will output for 10s, then 5s timeout = red at ~16s)"
echo ""

# Track status changes
last_status=""
status_changes=()
green_count=0
red_count=0

# Monitor for 22 seconds (10s output + 5s timeout + 7s buffer)
for i in $(seq 1 22); do
    status=$(get_status)

    # Count status occurrences
    if [[ "$status" == "green" ]]; then
        green_count=$((green_count + 1))
    elif [[ "$status" == "red" ]]; then
        red_count=$((red_count + 1))
    fi

    # Log status changes
    if [[ "$status" != "$last_status" ]]; then
        if [[ -n "$last_status" ]]; then
            log "Status changed: $last_status → $status (at ${i}s)"
            status_changes+=("$i:$last_status→$status")
        else
            log "Initial status: $status"
        fi
        last_status="$status"
    fi

    # Visual progress
    if [[ "$status" == "green" ]]; then
        echo -ne "\r  [$i/22s] 🟢 Active (outputting)    "
    else
        echo -ne "\r  [$i/22s] 🔴 Idle (silent)          "
    fi

    sleep 1
done
echo ""
echo ""

# Analyze results
log "=========================================="
log "Results Analysis"
log "=========================================="
echo ""
log "Green (active) samples: $green_count"
log "Red (idle) samples: $red_count"
log "Status changes detected: ${#status_changes[@]}"
for change in "${status_changes[@]}"; do
    log "  - $change"
done
echo ""

# Test 1: Should have seen green status during output phase
if [[ $green_count -ge 5 ]]; then
    pass "Detected active output (green status seen $green_count times)"
else
    fail "Should have detected active output, only saw green $green_count times"
fi

# Test 2: Should have seen red status during/after silence
if [[ $red_count -ge 3 ]]; then
    pass "Detected silence (red status seen $red_count times)"
else
    fail "Should have detected silence, only saw red $red_count times"
fi

# Test 3: Should have seen at least one status change
if [[ ${#status_changes[@]} -ge 1 ]]; then
    pass "Status transitions detected (${#status_changes[@]} changes)"
else
    fail "Should have detected status transitions"
fi

# Test 4: Final status should be mostly red (simulator stopped)
# Sample 5 times over 3 seconds to handle timing variations
red_samples=0
for i in 1 2 3 4 5; do
    sleep 0.6
    status=$(get_status)
    [[ "$status" == "red" ]] && red_samples=$((red_samples + 1))
done
log "Final status check: $red_samples/5 samples were red"
if [[ "$red_samples" -ge 4 ]]; then
    pass "Final status is mostly red ($red_samples/5 - correctly detected silence)"
else
    fail "Final status should be mostly red, only $red_samples/5 samples were red"
fi

# Test 5: Verify process cleanup works
log ""
log "Killing session to verify cleanup..."
tmux kill-session -t "$SESSION" 2>/dev/null
trap - EXIT
sleep 0.5
remaining=$(pgrep -f "tmux set -t.*$SESSION" 2>/dev/null | wc -l)
if [[ "$remaining" -eq 0 ]]; then
    pass "Processes cleaned up after session kill"
else
    fail "Found $remaining orphaned processes"
fi

# Summary
echo ""
echo "=========================================="
echo "Final Results: $PASS passed, $FAIL failed"
echo "=========================================="

if [[ "$FAIL" -eq 0 ]]; then
    echo "All tests passed!"
    exit 0
else
    echo "Some tests failed!"
    exit 1
fi
