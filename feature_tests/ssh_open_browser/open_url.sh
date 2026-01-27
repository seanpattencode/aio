#!/bin/bash
# Open URL in browser on any device via SSH
# Usage: aio ssh <host> 'open_url.sh "https://example.com"'
#    or: ./open_url.sh "https://example.com"  (locally)

URL="${1:-https://google.com}"

# WSL -> Windows
if grep -qi microsoft /proc/version 2>/dev/null; then
    /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe Start-Process "$URL"
# macOS
elif [[ "$OSTYPE" == darwin* ]]; then
    open "$URL"
# Android/Termux
elif [[ -n "$TERMUX_VERSION" ]]; then
    termux-open-url "$URL"
# Linux with display
elif [[ -n "$DISPLAY" ]]; then
    xdg-open "$URL"
# Linux via SSH (try common displays)
else
    for d in 0 1 2; do
        DISPLAY=:$d xdg-open "$URL" 2>/dev/null && exit 0
    done
    echo "No display found" >&2; exit 1
fi
