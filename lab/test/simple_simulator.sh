#!/bin/bash
# Simple LLM simulator with predictable timing
# Usage: ./simple_simulator.sh [duration_seconds]

DURATION=${1:-10}
END=$((SECONDS + DURATION))

echo "LLM Simulator starting (${DURATION}s run)..."
echo ""

# Output text every 0.5s until duration reached
while [[ $SECONDS -lt $END ]]; do
    echo "[$(date +%H:%M:%S)] Processing... ($((END - SECONDS))s remaining)"
    sleep 0.5
done

echo ""
echo "Done! Now going silent..."
echo "> "

# Silent forever (wait for input)
exec cat
