# SSH Remote Browser Opening

Open URLs in the default browser on remote devices via SSH.

## Commands by Platform

| Platform | Command | Notes |
|----------|---------|-------|
| **macOS** | `open "URL"` | Built-in, always works |
| **Android/Termux** | `termux-open-url "URL"` | Needs `pkg install termux-api` |
| **Linux (local)** | `xdg-open "URL"` | Freedesktop standard |
| **Linux (SSH)** | `DISPLAY=:0 xdg-open "URL"` | Must specify display |
| **WSL -> Windows** | `/mnt/c/Windows/.../powershell.exe Start-Process "URL"` | Full path required |

## Why DISPLAY is needed over SSH

SSH sessions have no GUI context. Linux X11 apps need to know which display to render to. Locally, `$DISPLAY` is set (usually `:0` or `:1`). Over SSH, it's empty.

## Full WSL PowerShell path

```
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
```

Non-interactive SSH shells don't have Windows paths in `$PATH`, so the full path is required.

## Examples with aio ssh

```bash
# Mac
aio ssh mac 'open "https://example.com"'

# Android
aio ssh termux 'termux-open-url "https://example.com"'

# Linux desktop
aio ssh ubuntu 'DISPLAY=:0 xdg-open "https://example.com"'

# WSL
aio ssh wsl '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe Start-Process "https://example.com"'

# All hosts (using universal script)
aio ssh all './open_url.sh "https://example.com"'
```

## Universal script

See `open_url.sh` - auto-detects platform and uses correct method.
