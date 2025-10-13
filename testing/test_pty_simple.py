#!/usr/bin/env python3
"""Simple PTY test"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("Test 1: Import aios.py...")
try:
    import aios
    print("✓ Import successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTest 2: Create test tmux session...")
try:
    import libtmux
    server = libtmux.Server()

    # Clean up
    if sess := next((s for s in server.sessions if s.name == "test-pty"), None):
        sess.kill()
        time.sleep(0.5)

    # Create session
    session = server.new_session("test-pty", window_command="bash", attach=False)
    time.sleep(1)
    print(f"✓ Session: {session.name}")

except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTest 3: Create PTY terminal...")
try:
    master = aios.get_or_create_terminal("test-pty")
    print(f"✓ PTY master fd: {master}")
    print(f"✓ Terminal sessions: {list(aios._terminal_sessions.keys())}")

except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTest 4: Write to PTY and read back...")
try:
    import os
    time.sleep(0.5)

    # Write a command
    os.write(master, b"echo hello\n")
    time.sleep(0.5)

    # Read output
    os.set_blocking(master, False)
    output = b""
    for _ in range(5):
        try:
            chunk = os.read(master, 4096)
            if chunk:
                output += chunk
        except BlockingIOError:
            pass
        time.sleep(0.1)

    if output:
        print(f"✓ Read {len(output)} bytes")
        print(f"Output: {output[:200]}")
    else:
        print("✗ No output received")

except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()

print("\n✓ Basic PTY test complete")
