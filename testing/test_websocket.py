#!/usr/bin/env python3
"""Test websocket terminal connection"""
import asyncio, websockets, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def test_websocket():
    """Test websocket connection to terminal"""
    import aios

    # Create test session
    print("1. Creating test tmux session...")
    import libtmux
    server = libtmux.Server()

    # Cleanup
    if sess := next((s for s in server.sessions if s.name == "test-ws"), None):
        sess.kill()
        time.sleep(0.5)

    # Create new session
    session = server.new_session("test-ws", window_command="bash", attach=False)
    time.sleep(1)
    print(f"✓ Created session: {session.name}")

    # Start websocket server
    print("\n2. Starting websocket server...")
    aios.start_ws_server()
    time.sleep(2)

    if not aios.ws_server_running:
        print("✗ Server not running")
        return False

    print(f"✓ Server running on port {aios.ws_port}")

    # Test websocket connection
    print("\n3. Testing websocket connection...")
    try:
        uri = f"ws://localhost:{aios.ws_port}/attach/test-ws"
        async with websockets.connect(uri) as ws:
            print(f"✓ Connected to {uri}")

            # Send a command
            print("\n4. Sending test command...")
            command = b"echo 'TEST_OUTPUT_12345'\n"
            await ws.send(command)
            print(f"✓ Sent: {command.decode()}")

            # Wait for response
            print("\n5. Waiting for response...")
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    output = msg.decode('utf-8', errors='ignore') if isinstance(msg, bytes) else str(msg)
                    print(f"Received: {repr(output[:100])}")

                    if 'TEST_OUTPUT_12345' in output:
                        print("\n✓ TEST PASSED: Received expected output")
                        return True
                except asyncio.TimeoutError:
                    continue

            print("\n✗ TEST FAILED: Did not receive expected output")
            return False

    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        session.kill()

# Run test
print("="*60)
print("WEBSOCKET TERMINAL TEST")
print("="*60)
print()

try:
    result = asyncio.run(test_websocket())
    if result:
        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED")
        print("="*60)
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("✗ TEST FAILED")
        print("="*60)
        sys.exit(1)
except KeyboardInterrupt:
    print("\n✗ Test interrupted")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ Test error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
