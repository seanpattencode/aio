#!/usr/bin/env python3
"""Test HTTP and WebSocket servers"""
import sys, time, asyncio, websockets, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("="*60)
print("Testing Dual-Server Setup")
print("="*60)
print()

# Import aios
import aios
import libtmux

# Create test session
print("1. Creating test tmux session...")
server = libtmux.Server()
if sess := next((s for s in server.sessions if s.name == "test-http"), None):
    sess.kill()
    time.sleep(0.5)

session = server.new_session("test-http", window_command="bash", attach=False)
time.sleep(1)
print(f"✓ Created session: {session.name}")

# Start servers
print("\n2. Starting HTTP and WebSocket servers...")
aios.start_ws_server()
time.sleep(2)

if not aios.ws_server_running:
    print("✗ WebSocket server not running")
    sys.exit(1)

print(f"✓ Servers started")
print(f"  HTTP:      http://localhost:{aios.ws_port}")
print(f"  WebSocket: ws://localhost:{aios.ws_port + 1}")

# Test HTTP server
print("\n3. Testing HTTP server...")
try:
    # Create test HTML
    Path("terminal.html").write_text("<html><body>TEST</body></html>")

    response = urllib.request.urlopen(f"http://localhost:{aios.ws_port}/terminal.html")
    content = response.read().decode()

    if "TEST" in content:
        print("✓ HTTP server working - received HTML")
    else:
        print("✗ HTTP server returned unexpected content")
        sys.exit(1)
except Exception as e:
    print(f"✗ HTTP server test failed: {e}")
    sys.exit(1)

# Test WebSocket
print("\n4. Testing WebSocket connection...")
async def test_ws():
    try:
        uri = f"ws://localhost:{aios.ws_port + 1}/attach/test-http"
        async with websockets.connect(uri) as ws:
            print(f"✓ Connected to {uri}")

            # Send test command
            await ws.send(b"echo WS_TEST_OK\n")

            # Wait for response
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    output = msg.decode('utf-8', errors='ignore') if isinstance(msg, bytes) else str(msg)
                    if 'WS_TEST_OK' in output:
                        print("✓ WebSocket working - received echo")
                        return True
                except asyncio.TimeoutError:
                    continue

            print("✗ Did not receive expected output")
            return False
    except Exception as e:
        print(f"✗ WebSocket test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(test_ws())

# Cleanup
session.kill()

if result:
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED - HTTP and WebSocket working!")
    print("="*60)
    sys.exit(0)
else:
    print("\n" + "="*60)
    print("✗ TESTS FAILED")
    print("="*60)
    sys.exit(1)
