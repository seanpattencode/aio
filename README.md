# AIO - AI Agent Manager

Manage AI coding agents (Claude, Codex, Gemini, Aider) with tmux sessions, SSH remotes, and git workflows.

## Install

**One-liner (Linux/macOS/WSL):**
```bash
curl -fsSL https://raw.githubusercontent.com/seanpattencode/aio/main/install.sh | bash
```

Installs: tmux, node, claude, codex, gemini, aio. Prompts for sudo if needed. Works without root (installs to ~/.local).

**Mac:** Install Homebrew first: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`

**Termux:** `pkg install git python && git clone https://github.com/seanpattencode/aio && cd aio && bash install.sh`

**Windows:** Install [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) first, then use the one-liner.

## Quick Start
```bash
aio                    # Show help
aio l                  # Start Claude session
aio c                  # Start Codex session
aio ssh                # Manage SSH connections
aio ssh mypc user@ip   # Save SSH host
aio ssh 0              # Connect to host 0
aio run 0 "task"       # Run task on remote host
aio push "msg"         # Git commit + push
```

## Notes
- Directory names starting with `.` may cause issues
- `aio push` may show failure on Mac but still work

## Recommendatations


on gemini set
tools.shell.enableInteractiveShell: false
this prevents waiting for interactive commands forever
tools.autoAccept: true
and change the model to be pro preview permanently





