# Claude Native Installer Fails on Termux

## Issue

Claude Code's native installer downloads a Linux aarch64 binary that won't run on Termux/Android.

```
file ~/.local/share/claude/versions/2.1.27
ELF 64-bit LSB executable, ARM aarch64, interpreter /lib/ld-linux-aarch64.so.1
```

The binary expects the standard Linux dynamic linker at `/lib/ld-linux-aarch64.so.1`, but Termux uses its own linker at `/data/data/com.termux/files/usr/lib/ld-android.so`.

## Solution

Use npm instead of the native installer:

```bash
rm -rf ~/.local/share/claude ~/.local/bin/claude
npm install -g @anthropic-ai/claude-code
```

## Why This Happens

Termux is not standard Linux - it's a terminal emulator running in Android's app sandbox. All libraries live under `/data/data/com.termux/files/usr/` rather than `/lib` or `/usr/lib`. Native binaries compiled for Linux assume standard paths and fail.

## Alternative (Not Recommended)

Could patch the binary with `patchelf --set-interpreter`, but npm install is simpler and auto-updates correctly.
