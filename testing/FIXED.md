# Terminal Fix - ERR_EMPTY_RESPONSE Fixed

## Problem

Browser was showing "ERR_EMPTY_RESPONSE" when accessing http://localhost:7681/terminal.html

## Root Cause

The `process_request` callback in websockets library v13+ has a different signature and return format that wasn't working correctly for serving HTTP content alongside WebSocket connections.

## Solution

Switched to **dual-server architecture** (git daemon style):
- **HTTP Server** (port 7681) - Serves terminal.html
- **WebSocket Server** (port 7682) - Handles PTY connections

This follows the "do one thing well" Unix philosophy and avoids the complexity of mixing HTTP and WebSocket on the same port.

## Changes Made

### 1. Added HTTP Server (aios.py:257-280)

```python
from http.server import HTTPServer, BaseHTTPRequestHandler

class TerminalHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/terminal.html":
            # Serve terminal.html
            ...
    def log_message(self, *args): pass

class ReuseHTTPServer(HTTPServer):
    allow_reuse_address = True  # Allow port reuse

def http_server_thread():
    httpd = ReuseHTTPServer(('localhost', ws_port), TerminalHTTPHandler)
    httpd.serve_forever()
```

### 2. Separated WebSocket Server (aios.py:282-298)

```python
def ws_server_thread():
    """WebSocket server on port ws_port + 1"""
    async with websockets.serve(ws_handler, "localhost", ws_port + 1):
        ws_server_running = True
        await asyncio.Future()
```

### 3. Updated Start Function (aios.py:300-306)

```python
def start_ws_server():
    """Start both HTTP and WebSocket servers"""
    Thread(target=http_server_thread, daemon=True).start()
    Thread(target=ws_server_thread, daemon=True).start()
    sleep(1)
```

### 4. Updated HTML Generation (aios.py:343)

```python
# WebSocket now connects to port 7682
const ws = new WebSocket('ws://localhost:7682/attach/' + session);
```

## Architecture

```
Browser
   ↓
   ├─→ HTTP GET /terminal.html → HTTP Server (port 7681)
   │                               Returns HTML
   │
   └─→ WebSocket /attach/session → WS Server (port 7682)
                                     ↕ PTY
                                     bash process
```

## Testing

```bash
# Quick test
python3 test_final.py

# Full integration test
./test_integration.sh
```

Both show:
```
✓ ALL TESTS PASSED
```

## Line Count

**570 lines** (increased from 554 due to separate HTTP server, but cleaner architecture)

## Benefits of Dual-Server Approach

1. **Simpler**: Each server does one thing
2. **Git-inspired**: Like `git daemon`, separate concerns
3. **Debuggable**: Can test HTTP and WS independently
4. **No library quirks**: Avoids websockets library versioning issues
5. **Port reuse**: Proper SO_REUSEADDR handling

## Usage

```bash
./aios.py
```

Then type:
```
demo: Interactive shell | bash
run demo
attach demo
```

Browser opens with working terminal at http://localhost:7681/terminal.html

The WebSocket connection to ws://localhost:7682 provides real-time PTY interaction.

## Summary

Fixed ERR_EMPTY_RESPONSE by switching from single-port process_request approach to clean dual-server architecture:
- HTTP server (7681) for HTML
- WebSocket server (7682) for PTY

This follows Unix philosophy and git's design patterns for separate, composable services.
