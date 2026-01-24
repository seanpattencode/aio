#!/bin/bash
cd "$(dirname "$0")"

echo "=== COLD: Monolith ==="
for i in 1 2 3; do /usr/bin/time -f '%e' python3 monolith.py a 2>&1 | tail -1; done

echo -e "\n=== COLD: Split ==="
for i in 1 2 3; do /usr/bin/time -f '%e' python3 split/main.py a 2>&1 | tail -1; done

echo -e "\n--- Starting MONOLITH daemon ---"
pkill -f "warm.py" 2>/dev/null; rm -f /tmp/test_warm.sock
python3 warm.py monolith.py &
sleep 2

echo "=== WARM: Monolith ==="
for i in 1 2 3; do /usr/bin/time -f '%e' sh -c 'echo "a" | nc -U /tmp/test_warm.sock' 2>&1 | tail -1; done

echo -e "\n--- Starting SPLIT daemon ---"
pkill -f "warm.py" 2>/dev/null; rm -f /tmp/test_warm.sock; sleep 1
python3 warm.py split/main.py &
sleep 2

echo "=== WARM: Split ==="
for i in 1 2 3; do /usr/bin/time -f '%e' sh -c 'echo "a" | nc -U /tmp/test_warm.sock' 2>&1 | tail -1; done

pkill -f "warm.py" 2>/dev/null; rm -f /tmp/test_warm.sock
echo -e "\nDone"
