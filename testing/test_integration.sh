#!/bin/bash
# Complete integration test for AIOS terminal attach

echo "=========================================="
echo "AIOS Terminal Integration Test"
echo "=========================================="
echo

# Cleanup
echo "1. Cleaning up..."
tmux kill-session -t aios-* 2>/dev/null || true
rm -f terminal.html
sleep 1

# Create a simple test task
echo "2. Creating test task..."
cat > /tmp/terminal_test.json <<'EOF'
{
  "name": "shelltest",
  "steps": [
    {"desc": "Create test file", "cmd": "echo 'Terminal test ready' > test.txt"},
    {"desc": "Show content", "cmd": "cat test.txt"},
    {"desc": "Wait for interaction", "cmd": "sleep 300"}
  ]
}
EOF
echo "✓ Created test task"

# Start AIOS in background and run the task
echo
echo "3. Starting AIOS and running test job..."
timeout 15 python3 <<'PYTHON' &
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

# Load and queue the task
import json
with open('/tmp/terminal_test.json') as f:
    task = json.load(f)

from aios import task_queue, run_simple_mode
task_queue.put(task)

# Give it time to start
import threading
from aios import execute_task
t = threading.Thread(target=execute_task, args=(task,), daemon=True)
t.start()
time.sleep(5)

print("✓ Task started, session should be running")
sys.exit(0)
PYTHON

# Wait for task to start
sleep 6

# Check if session exists
echo "4. Verifying tmux session..."
if tmux list-sessions 2>/dev/null | grep -q "aios-shelltest"; then
    SESSION=$(tmux list-sessions | grep "aios-shelltest" | cut -d: -f1)
    echo "✓ Found session: $SESSION"
else
    echo "✗ No session found"
    exit 1
fi

# Test websocket connection
echo
echo "5. Testing terminal attachment..."
python3 <<PYTEST
import asyncio, websockets, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

async def test():
    import aios, libtmux

    # Find the session
    server = libtmux.Server()
    session = next((s for s in server.sessions if 'shelltest' in s.name), None)
    if not session:
        print("✗ No session found")
        return False

    print(f"✓ Found session: {session.name}")

    # Start websocket server
    aios.start_ws_server()
    time.sleep(2)

    if not aios.ws_server_running:
        print("✗ Server not running")
        return False

    print("✓ Server running")

    # Test websocket
    uri = f"ws://localhost:{aios.ws_port}/attach/{session.name}"
    try:
        async with websockets.connect(uri) as ws:
            print("✓ Connected to terminal")

            # Send test command
            await ws.send(b"echo INTEGRATION_TEST_OK\n")

            # Wait for response
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    output = msg.decode('utf-8', errors='ignore') if isinstance(msg, bytes) else str(msg)
                    if 'INTEGRATION_TEST_OK' in output:
                        print("✓ Terminal is interactive and working")
                        return True
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

    return False

result = asyncio.run(test())
sys.exit(0 if result else 1)
PYTEST

TEST_RESULT=$?

echo
if [ $TEST_RESULT -eq 0 ]; then
    echo "=========================================="
    echo "✓ ALL INTEGRATION TESTS PASSED"
    echo "=========================================="
    echo
    echo "The terminal is working correctly!"
    echo "You can manually test by:"
    echo "  1. Run: ./aios.py"
    echo "  2. Type: shelltest: Interactive | bash"
    echo "  3. Type: run shelltest"
    echo "  4. Type: attach shelltest"
else
    echo "=========================================="
    echo "✗ INTEGRATION TEST FAILED"
    echo "=========================================="
fi

# Cleanup
echo
echo "Cleaning up..."
tmux kill-session -t aios-* 2>/dev/null || true
rm -f /tmp/terminal_test.json

exit $TEST_RESULT
