# AIOS Interactive Terminal Attachment

## Overview

AIOS now includes an integrated websocket PTY server that allows you to attach to running jobs and interact with them in real-time through a web browser.

## Quick Start

```bash
# 1. Start AIOS
./aios.py
```

Then in the AIOS prompt (don't type the ❯), enter:
```
demo: Start | echo "Type 'exit' to quit"
demo: Interactive | bash
run demo
attach demo
```

**Important:** The `❯` character is just the prompt indicator shown in examples. Don't type it!

Your browser opens with an interactive terminal connected to the job's tmux session!

## Features

- **Multiple Sessions**: Each job runs in its own tmux session
- **Real-time Interaction**: Type commands, see output immediately  
- **Persistent Monitoring**: AIOS continues tracking job status
- **Auto-generated Terminal**: Minimal HTML/JS client (no dependencies)
- **Direct tmux Bridge**: Websocket connects directly to tmux sessions

## Architecture

```
┌─────────────┐      WebSocket       ┌──────────────┐
│   Browser   │◄────────────────────►│ AIOS Server  │
│ terminal.html│   JSON messages     │   Port 7681  │
└─────────────┘                      └──────┬───────┘
                                            │
                                     tmux.send_keys()
                                     tmux.capture_pane()
                                            │
                                            ▼
                                    ┌──────────────┐
                                    │ Tmux Session │
                                    │  aios-demo-* │
                                    └──────────────┘
```

## Commands

### In AIOS TUI

- `attach <job>` - Opens web terminal for the specified job
- Job must be running (in tmux session)
- Browser opens automatically to http://localhost:7681/terminal.html

### In Web Terminal

- Type commands normally
- Press Enter to send
- Commands execute in job's tmux session
- Output updates in real-time (100ms polling)

## Technical Details

**Event-Driven Architecture:**
- No polling - 100% event-driven using tmux `pipe-pane`
- Binary WebSocket messages (ArrayBuffer/Uint8Array)
- XTerm.js for full terminal emulation
- HTTP + WebSocket on single port (7681)

**Protocol:**
```
Browser: HTTP GET /terminal.html
Server:  Returns HTML with xterm.js

Browser: WebSocket /attach/<session> (binary mode)
Server:  tmux pipe-pane → FIFO → WebSocket
Browser: Sends keystrokes as binary (TextEncoder)
Server:  Forwards to tmux session
```

**Implementation:**
- Event-driven: tmux pipe-pane streams to FIFO
- FIFO reads are non-blocking, async
- Binary messages (no JSON overhead)
- XTerm.js via CDN (no local dependencies)
- HTTP + WebSocket on same port

## Use Cases

**1. Interactive Development**

Type in AIOS prompt:
```
code: Setup | cd project && python3 -m venv venv
code: Activate | source venv/bin/activate
code: Shell | bash
run code
attach code
```

Now you're in an interactive shell!

**2. Long-running Processes**
```
train: Start training | python train.py --epochs 100
run train
attach train
```

Monitor and interact with training in real-time.

**3. Debugging**
```
debug: Run with debugger | python -m pdb script.py
run debug
attach debug
```

Interactive debugging session in browser.

**4. Multi-session Development**

In first AIOS instance:
```
backend: Start server | python manage.py runserver
run backend
attach backend
```

In second AIOS instance:
```
frontend: Start dev | npm run dev
run frontend
attach frontend
```

Both monitored by AIOS, both interactive!

## Limitations

- Browser required (opens automatically)
- WebSocket port 7681 must be available
- Requires internet for xterm.js CDN (first load only)
- Requires tmux pipe-pane support

## Git-Inspired Design

Like `git daemon` for serving repositories, AIOS now includes a minimal server for serving terminal access:

- Single integrated binary
- Starts on-demand
- Runs in background
- No configuration needed
- Direct library usage (websockets + asyncio)

## Files

- `aios.py` - 518 lines (integrated HTTP + WebSocket server)
- `terminal.html` - 938 bytes (auto-generated, xterm.js from CDN)
- Server on port 7681 (HTTP + WebSocket)

## Performance

- **Zero Polling**: Event-driven via tmux pipe-pane
- **Binary Protocol**: Direct byte streams, no JSON parsing
- **Instant Updates**: FIFO streams data immediately
- **Low Latency**: Async I/O, non-blocking reads
- **Full Terminal**: XTerm.js supports colors, cursor, etc.

