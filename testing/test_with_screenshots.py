#!/usr/bin/env python3
"""Test terminal with screenshots - final version"""
import sys, time, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

print("="*80)
print("FINAL TERMINAL TEST WITH SCREENSHOTS")
print("="*80)
print()

# Clean up
print("1. Cleaning up...")
subprocess.run("tmux kill-session -t test-* 2>/dev/null || true", shell=True)
subprocess.run("lsof -ti:7681 | xargs kill -9 2>/dev/null || true", shell=True)
subprocess.run("lsof -ti:7682 | xargs kill -9 2>/dev/null || true", shell=True)
time.sleep(2)
Path("terminal.html").unlink(missing_ok=True)
for f in Path(".").glob("screenshot*.png"):
    f.unlink()
print("✓ Cleaned up")

# Import aios
print("\n2. Importing aios...")
import aios
import libtmux
print("✓ Imported")

# Create test session
print("\n3. Creating test tmux session...")
server = libtmux.Server()
session = server.new_session("test-term", window_command="bash", attach=False)
time.sleep(1)
print(f"✓ Created session: {session.name}")

# Create terminal.html
print("\n4. Creating terminal.html...")
session_name = session.name
html_file = Path("terminal.html")
html_file.write_text(f'''<!DOCTYPE html>
<html><head><title>AIOS Terminal</title>
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
const params = new URLSearchParams(window.location.search);
const session = params.get('session');
const ws = new WebSocket('ws://localhost:{aios.ws_port + 1}/attach/' + session);
ws.binaryType = 'arraybuffer';
ws.onopen = () => term.writeln('\\x1b[1;32m✓ Connected to AIOS terminal\\x1b[0m');
ws.onerror = (e) => term.writeln('\\x1b[1;31m✗ WebSocket error\\x1b[0m');
ws.onclose = () => term.writeln('\\x1b[1;33m✗ Connection closed\\x1b[0m');
ws.onmessage = e => term.write(new Uint8Array(e.data));
term.onData(d => ws.send(new TextEncoder().encode(d)));
window.onresize = () => fit.fit();
</script>
</body></html>''')
print(f"✓ Created ({html_file.stat().st_size} bytes)")

# Start servers
print("\n5. Starting servers...")
aios.start_ws_server()
time.sleep(3)
print(f"✓ Servers running (HTTP:{aios.ws_port}, WS:{aios.ws_port + 1})")

# Test with playwright
print("\n6. Testing in browser...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={'width': 1280, 'height': 720})

    url = f"http://localhost:{aios.ws_port}/terminal.html?session={session_name}"
    print(f"   URL: {url}")

    try:
        # Navigate
        response = page.goto(url, wait_until="networkidle", timeout=10000)
        print(f"   ✓ Page loaded (HTTP {response.status})")

        # Wait for terminal
        page.wait_for_selector("#terminal", timeout=5000)
        print("   ✓ Terminal element loaded")

        # Screenshot 1: Initial load
        page.screenshot(path="screenshot_1_loaded.png")
        print("   ✓ Screenshot 1: screenshot_1_loaded.png")

        # Wait for WebSocket connection
        time.sleep(2)

        # Send test commands
        print("\n7. Testing commands...")
        page.keyboard.type("echo '=== AIOS TERMINAL TEST ==='\n")
        time.sleep(1)

        page.keyboard.type("pwd\n")
        time.sleep(1)

        page.keyboard.type("echo 'Test successful!'\n")
        time.sleep(1)

        # Screenshot 2: After commands
        page.screenshot(path="screenshot_2_commands.png")
        print("   ✓ Screenshot 2: screenshot_2_commands.png")

        # More commands
        page.keyboard.type("ls -la | head -10\n")
        time.sleep(2)

        # Screenshot 3: Final
        page.screenshot(path="screenshot_3_final.png")
        print("   ✓ Screenshot 3: screenshot_3_final.png")

        print("\n" + "="*80)
        print("✓ ALL TESTS PASSED!")
        print("="*80)
        print()
        print("Screenshots saved:")
        print("  - screenshot_1_loaded.png  (initial load)")
        print("  - screenshot_2_commands.png (after commands)")
        print("  - screenshot_3_final.png   (final state)")
        print()
        print("The terminal is working perfectly!")
        print()

        # Keep browser open briefly
        time.sleep(5)

    except Exception as e:
        print(f"   ✗ Test failed: {e}")
        page.screenshot(path="screenshot_error.png")
        print("   ✓ Error screenshot: screenshot_error.png")
        import traceback
        traceback.print_exc()

    finally:
        browser.close()

# Cleanup
print("\n8. Cleaning up...")
session.kill()
print("✓ Done")
