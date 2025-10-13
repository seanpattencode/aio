#!/usr/bin/env python3
"""Debug terminal with playwright screenshots"""
import sys, time, asyncio, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

print("="*80)
print("TERMINAL DEBUG WITH SCREENSHOTS")
print("="*80)
print()

# Clean up
print("1. Cleaning up...")
subprocess.run("tmux kill-session -t aios-* 2>/dev/null || true", shell=True)
subprocess.run("lsof -ti:7681 | xargs kill -9 2>/dev/null || true", shell=True)
subprocess.run("lsof -ti:7682 | xargs kill -9 2>/dev/null || true", shell=True)
time.sleep(2)
Path("terminal.html").unlink(missing_ok=True)
print("✓ Cleaned up")

# Import aios
print("\n2. Importing aios...")
import aios
import libtmux
print("✓ Imported")

# Create test session
print("\n3. Creating test tmux session...")
server = libtmux.Server()
session = server.new_session("aios-demo-20251012_223542", window_command="bash", attach=False)
time.sleep(1)
print(f"✓ Created session: {session.name}")

# Test 1: Create terminal.html FIRST
print("\n4. Creating terminal.html BEFORE starting server...")
session_name = session.name
html_file = Path("terminal.html")
html_content = f'''<!DOCTYPE html>
<html><head><title>AIOS Terminal Debug</title>
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
ws.onopen = () => term.writeln('\\x1b[1;32mConnected to AIOS\\x1b[0m');
ws.onerror = (e) => term.writeln('\\x1b[1;31mWebSocket error\\x1b[0m');
ws.onclose = () => term.writeln('\\x1b[1;33mConnection closed\\x1b[0m');
ws.onmessage = e => term.write(new Uint8Array(e.data));
term.onData(d => ws.send(new TextEncoder().encode(d)));
window.onresize = () => fit.fit();
</script>
</body></html>'''
html_file.write_text(html_content)
print(f"✓ Created terminal.html ({html_file.stat().st_size} bytes)")
print(f"  Path: {html_file.absolute()}")

# Start servers
print("\n5. Starting HTTP and WebSocket servers...")
aios.start_ws_server()
time.sleep(3)

if not aios.ws_server_running:
    print("✗ WebSocket server not running")
    sys.exit(1)

print(f"✓ Servers started:")
print(f"   HTTP:      http://localhost:{aios.ws_port}")
print(f"   WebSocket: ws://localhost:{aios.ws_port + 1}")

# Test HTTP server directly
print("\n6. Testing HTTP server directly...")
import urllib.request
try:
    url = f"http://localhost:{aios.ws_port}/terminal.html"
    response = urllib.request.urlopen(url, timeout=5)
    content = response.read().decode()
    print(f"✓ HTTP server responded ({len(content)} bytes)")
    if "AIOS Terminal" in content:
        print("✓ HTML content looks correct")
    else:
        print("✗ HTML content doesn't match expected")
        print(f"  First 200 chars: {content[:200]}")
except Exception as e:
    print(f"✗ HTTP server test failed: {e}")
    print("\nDebugging HTTP server...")

    # Check if file exists
    if html_file.exists():
        print(f"✓ terminal.html exists: {html_file.absolute()}")
        print(f"  Size: {html_file.stat().st_size} bytes")
    else:
        print(f"✗ terminal.html doesn't exist")

    sys.exit(1)

# Test with playwright
print("\n7. Testing with Playwright browser...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = context.new_page()

    # Enable console logging
    page.on("console", lambda msg: print(f"   Browser console: {msg.text}"))

    url = f"http://localhost:{aios.ws_port}/terminal.html?session={session_name}"
    print(f"   Navigating to: {url}")

    try:
        # Navigate with timeout
        response = page.goto(url, wait_until="networkidle", timeout=10000)
        print(f"   ✓ Page loaded (status: {response.status})")

        # Wait for xterm to load
        page.wait_for_selector("#terminal", timeout=5000)
        print("   ✓ Terminal element found")

        # Take screenshot
        screenshot_path = "screenshot_terminal.png"
        page.screenshot(path=screenshot_path)
        print(f"   ✓ Screenshot saved: {screenshot_path}")

        # Wait a bit for WebSocket connection
        time.sleep(2)

        # Try to send a command
        print("\n8. Testing terminal interaction...")
        page.keyboard.type("echo 'TEST_COMMAND_OK'\n")
        time.sleep(1)

        # Take another screenshot
        screenshot_path2 = "screenshot_terminal_after_command.png"
        page.screenshot(path=screenshot_path2)
        print(f"   ✓ Screenshot saved: {screenshot_path2}")

        # Keep browser open for manual inspection
        print("\n9. Browser is open for manual testing...")
        print("   Press Ctrl+C to stop")
        time.sleep(300)

    except Exception as e:
        print(f"   ✗ Browser test failed: {e}")

        # Take error screenshot
        screenshot_path = "screenshot_error.png"
        page.screenshot(path=screenshot_path)
        print(f"   ✓ Error screenshot saved: {screenshot_path}")

        import traceback
        traceback.print_exc()

    finally:
        browser.close()

# Cleanup
print("\n10. Cleaning up...")
session.kill()
print("✓ Done")
