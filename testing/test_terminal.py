#!/usr/bin/env python3
"""Test PTY terminal functionality"""
import asyncio, websockets, sys, time
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

# Test 1: Check if aios.py can be imported
print("Test 1: Importing aios.py...")
try:
    import aios
    print("✓ Import successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Create a test tmux session for terminal to attach to
print("\nTest 2: Creating test tmux session...")
try:
    import libtmux
    server = libtmux.Server()

    # Clean up any existing test session
    if sess := next((s for s in server.sessions if s.name == "aios-test-term"), None):
        sess.kill()
        time.sleep(0.5)

    # Create new session
    session = server.new_session("aios-test-term", window_command="bash", attach=False)
    time.sleep(1)
    print(f"✓ Created session: {session.name}")

    # Send a test command
    pane = session.windows[0].panes[0]
    pane.send_keys("echo 'Terminal test ready'")
    time.sleep(0.5)

    # Capture output
    output = "\n".join(pane.capture_pane())
    print(f"✓ Session output: {output[:100]}")

except Exception as e:
    print(f"✗ Session creation failed: {e}")
    sys.exit(1)

# Test 3: Test PTY terminal creation
print("\nTest 3: Testing PTY terminal creation...")
try:
    master = aios.get_or_create_terminal("aios-test-term")
    print(f"✓ PTY created, master fd: {master}")

    # Try to read from it
    import os
    os.set_blocking(master, False)
    try:
        data = os.read(master, 1024)
        print(f"✓ Read {len(data)} bytes from PTY")
    except BlockingIOError:
        print("✓ PTY is non-blocking (no data yet)")

except Exception as e:
    print(f"✗ PTY creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Start websocket server
print("\nTest 4: Starting websocket server...")
try:
    aios.start_ws_server()
    time.sleep(2)

    if aios.ws_server_running:
        print(f"✓ WebSocket server running on port {aios.ws_port}")
    else:
        print("✗ WebSocket server not running")
        sys.exit(1)

except Exception as e:
    print(f"✗ Server start failed: {e}")
    sys.exit(1)

# Test 5: Generate terminal.html
print("\nTest 5: Generating terminal.html...")
try:
    html_file = Path("terminal.html")
    html_file.write_text(f'''<!DOCTYPE html>
<html><head><title>AIOS Terminal Test</title>
<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit/lib/xterm-addon-fit.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css"/>
<style>body{{margin:0;background:#000}}#terminal{{height:100vh}}</style>
</head><body>
<div id="terminal"></div>
<script>
const term = new Terminal();
const fit = new FitAddon.FitAddon();
term.loadAddon(fit);
term.open(document.getElementById('terminal'));
fit.fit();
const ws = new WebSocket('ws://localhost:{aios.ws_port}/attach/aios-test-term');
ws.binaryType = 'arraybuffer';
ws.onopen = () => console.log('WebSocket connected');
ws.onerror = (e) => console.error('WebSocket error:', e);
ws.onclose = () => console.log('WebSocket closed');
ws.onmessage = e => {{
    console.log('Received:', e.data);
    term.write(new Uint8Array(e.data));
}};
term.onData(d => {{
    console.log('Sending:', d);
    ws.send(new TextEncoder().encode(d));
}});
window.onresize = () => fit.fit();
</script>
</body></html>''')
    print(f"✓ Created terminal.html")
    print(f"\n✓ ALL TESTS PASSED!")
    print(f"\nTo test terminal interactively:")
    print(f"  1. Open http://localhost:{aios.ws_port}/terminal.html in your browser")
    print(f"  2. You should see a bash terminal")
    print(f"  3. Type commands and press enter")

except Exception as e:
    print(f"✗ HTML generation failed: {e}")
    sys.exit(1)

print("\nKeeping server running for manual testing... (Press Ctrl+C to stop)")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n✓ Test complete")
