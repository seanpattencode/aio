#!/bin/bash
# Test script for terminal attach feature

echo "==================================="
echo "AIOS Terminal Attach Test"
echo "==================================="
echo

# Cleanup
echo "1. Cleaning up old test sessions..."
tmux kill-session -t aios-shelltest-* 2>/dev/null || true
rm -f terminal.html
sleep 1

# Create test tmux session directly
echo "2. Creating test tmux session..."
tmux new-session -d -s "aios-shelltest-20251012_120000" -c "/home/seanpatten/projects/AIOS" bash
sleep 1

echo "3. Verifying session exists..."
if tmux has-session -t "aios-shelltest-20251012_120000" 2>/dev/null; then
    echo "✓ Session created successfully"
else
    echo "✗ Failed to create session"
    exit 1
fi

# Test terminal attachment
echo
echo "4. Testing terminal functionality..."
echo "   This will start the websocket server and open the terminal."
echo "   Press Ctrl+C after testing to cleanup."
echo

python3 << 'PYTHON_SCRIPT'
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import aios

# Start websocket server
print("Starting websocket server...")
aios.start_ws_server()
time.sleep(2)

if not aios.ws_server_running:
    print("✗ Server failed to start")
    sys.exit(1)

print(f"✓ Server running on port {aios.ws_port}")

# Generate HTML
print("Generating terminal.html...")
session_name = "aios-shelltest-20251012_120000"
url = f"http://localhost:{aios.ws_port}/terminal.html?session={session_name}"

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
const ws = new WebSocket('ws://localhost:{aios.ws_port}/attach/{session_name}');
ws.binaryType = 'arraybuffer';
ws.onopen = () => {{
    console.log('Connected');
    term.writeln('\\x1b[1;32m✓ Connected to AIOS terminal\\x1b[0m');
    term.writeln('\\x1b[1;33mType commands and press Enter\\x1b[0m');
    term.writeln('');
}};
ws.onerror = (e) => console.error('Error:', e);
ws.onclose = () => console.log('Closed');
ws.onmessage = e => term.write(new Uint8Array(e.data));
term.onData(d => ws.send(new TextEncoder().encode(d)));
window.onresize = () => fit.fit();
</script>
</body></html>''')

print(f"✓ Created terminal.html")
print()
print("="*60)
print(f"Opening browser at: {url}")
print("="*60)
print()
print("INSTRUCTIONS:")
print("  1. Your browser should open automatically")
print("  2. You should see a bash terminal")
print("  3. Try typing: echo 'hello from terminal'")
print("  4. Try: pwd")
print("  5. Try: ls")
print()
print("Press Ctrl+C here to stop the server and cleanup...")
print()

# Open browser
import webbrowser
webbrowser.open(url)

# Keep running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n✓ Stopping server...")

PYTHON_SCRIPT

echo
echo "5. Cleanup..."
tmux kill-session -t "aios-shelltest-20251012_120000" 2>/dev/null || true
echo
echo "✓ Test complete!"
