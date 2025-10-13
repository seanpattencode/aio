#!/usr/bin/env python3
"""Final complete test"""
import asyncio, websockets, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("="*60)
print("FINAL AIOS TERMINAL TEST")
print("="*60)
print()

# Clean up
print("1. Cleaning up old sessions...")
import subprocess
subprocess.run("tmux kill-session -t aios-* 2>/dev/null || true", shell=True)
subprocess.run("tmux kill-session -t test-* 2>/dev/null || true", shell=True)
time.sleep(1)
print("✓ Cleaned up")

# Import aios
print("\n2. Importing aios...")
import aios
import libtmux
print("✓ Imported")

# Create test session
print("\n3. Creating test tmux session...")
server = libtmux.Server()
session = server.new_session("test-final", window_command="bash", attach=False)
time.sleep(1)
print(f"✓ Created session: {session.name}")

# Start servers
print("\n4. Starting servers...")
aios.start_ws_server()
time.sleep(2)

if not aios.ws_server_running:
    print("✗ Servers not running")
    sys.exit(1)

print(f"✓ Servers running:")
print(f"   HTTP:      http://localhost:{aios.ws_port}")
print(f"   WebSocket: ws://localhost:{aios.ws_port + 1}")

# Test WebSocket
print("\n5. Testing WebSocket terminal...")
async def test():
    try:
        uri = f"ws://localhost:{aios.ws_port + 1}/attach/test-final"
        print(f"   Connecting to {uri}...")

        async with websockets.connect(uri) as ws:
            print("   ✓ Connected")

            # Send test command
            await ws.send(b"echo FINAL_TEST_SUCCESS\n")
            print("   ✓ Sent command")

            # Wait for response
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    output = msg.decode('utf-8', errors='ignore') if isinstance(msg, bytes) else str(msg)

                    if 'FINAL_TEST_SUCCESS' in output:
                        print("   ✓ Received echo response")
                        return True
                except asyncio.TimeoutError:
                    continue

            print("   ✗ Did not receive expected output")
            return False
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(test())

# Cleanup
print("\n6. Cleaning up...")
session.kill()

if result:
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED")
    print("="*60)
    print()
    print("The terminal is working correctly!")
    print("You can now use it with:")
    print("  ./aios.py")
    print("  Then type: demo: Interactive | bash")
    print("  Then type: run demo")
    print("  Then type: attach demo")
    print()
    sys.exit(0)
else:
    print("\n" + "="*60)
    print("✗ TEST FAILED")
    print("="*60)
    sys.exit(1)
