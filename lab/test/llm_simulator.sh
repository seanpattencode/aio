#!/bin/bash
# LLM CLI Simulator - mimics claude/codex/gemini output patterns
# Usage: ./llm_simulator.sh [duration_seconds]

DURATION=${1:-30}
START=$(date +%s)

# Simulated thinking phrases
THINKING=("⠋ thinking..." "⠙ thinking..." "⠹ thinking..." "⠸ thinking..." "⠼ thinking..." "⠴ thinking..." "⠦ thinking..." "⠧ thinking..." "⠇ thinking..." "⠏ thinking...")
WORKING=("working on it..." "analyzing code..." "searching files..." "reading context..." "generating response...")

# Print startup banner (like claude does)
echo "╭─────────────────────────────────────────╮"
echo "│  LLM Simulator v1.0                     │"
echo "│  Simulating AI assistant output         │"
echo "╰─────────────────────────────────────────╯"
echo ""
sleep 0.5

# Simulate prompt
echo -n "> "
sleep 0.3
echo "Help me understand this codebase"
echo ""
sleep 0.5

# Phase 1: Thinking spinner (5 seconds)
echo -n "  "
for i in {1..50}; do
    idx=$((i % ${#THINKING[@]}))
    echo -ne "\r  ${THINKING[$idx]}"
    sleep 0.1
done
echo -e "\r  ✓ Done thinking    "
echo ""
sleep 0.3

# Phase 2: Streaming response (simulates typing)
response="I'll analyze the codebase structure for you.

Looking at the project, I can see several key components:

1. **Main Entry Point** - The primary script handles CLI argument parsing
   and routes to different subcommands.

2. **Database Layer** - SQLite with WAL mode for concurrent access.
   Configuration and state are persisted here.

3. **Session Management** - Uses tmux for terminal multiplexing,
   allowing multiple agent sessions to run simultaneously.

4. **Activity Monitoring** - Tracks pane output to show status
   indicators (green = active, red = idle).

Let me search for more details..."

# Stream the response character by character with variable speed
while IFS= read -r -n1 char; do
    echo -n "$char"
    # Faster for spaces, slower for punctuation
    case "$char" in
        " ") sleep 0.02 ;;
        "."|","|":") sleep 0.08 ;;
        $'\n') sleep 0.15 ;;
        *) sleep 0.03 ;;
    esac
done <<< "$response"

echo ""
sleep 0.5

# Phase 3: Working indicator with file operations
echo ""
for msg in "${WORKING[@]}"; do
    NOW=$(date +%s)
    ELAPSED=$((NOW - START))
    if [[ $ELAPSED -ge $DURATION ]]; then
        break
    fi
    echo "  ⠏ $msg"
    sleep 1.5
done

# Phase 4: More output bursts until duration reached
while true; do
    NOW=$(date +%s)
    ELAPSED=$((NOW - START))
    if [[ $ELAPSED -ge $DURATION ]]; then
        break
    fi

    # Random code block output
    echo ""
    echo '```python'
    echo "# Found in src/main.py:${RANDOM:0:2}"
    echo "def process_request(data):"
    echo "    result = analyze(data)"
    echo "    return format_response(result)"
    echo '```'
    sleep 2

    # Check time again
    NOW=$(date +%s)
    ELAPSED=$((NOW - START))
    if [[ $ELAPSED -ge $DURATION ]]; then
        break
    fi

    # Thinking again
    echo ""
    echo -n "  "
    for i in {1..20}; do
        idx=$((i % ${#THINKING[@]}))
        echo -ne "\r  ${THINKING[$idx]}"
        sleep 0.1
    done
    echo -e "\r  ✓ Found relevant code"
    sleep 1
done

# Final output
echo ""
echo "────────────────────────────────────────"
echo "Analysis complete. The codebase follows"
echo "a modular design with clear separation"
echo "of concerns."
echo ""
echo "> "

# Stay idle (simulating waiting for next prompt)
# The pipe-pane monitor should detect this silence
exec cat
