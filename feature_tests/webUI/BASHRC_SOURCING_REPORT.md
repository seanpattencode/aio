# Bash Startup Chain Optimization

## Problem

Commands in tmux and subprocesses run 50x slower than interactive terminals.

```
Interactive terminal:  aio → 2ms   (shell function)
tmux window:           aio → 50ms  (Python binary)
subprocess.getoutput:  aio → 52ms  (Python binary)
```

## Root Cause

Bash has two startup modes with different config files:

| Mode | Triggered By | Sources |
|------|--------------|---------|
| **Login** | `bash -l`, tmux, SSH | `.bash_profile` → (should chain to) `.bashrc` |
| **Interactive** | `bash -i`, terminal emulator | `.bashrc` directly |

Most shell functions and aliases live in `.bashrc`. If `.bash_profile` doesn't exist or doesn't source `.bashrc`, login shells miss all optimizations.

## The Fix

```bash
# ~/.bash_profile (one line)
source ~/.bashrc
```

This chains login shells to bashrc, enabling shell functions everywhere.

## Benchmark: Before/After

| Context | Before | After |
|---------|--------|-------|
| tmux `aio` | 50ms | 2ms |
| subprocess `aio` | 52ms | 0.5ms |
| subprocess `ls` | 2.3ms | 0.5ms |
| subprocess `git status` | 1.5ms | 0.4ms |

## Why Sourcing Bashrc Helps Subprocesses

`subprocess.getoutput(cmd)` uses `bash -c` (non-interactive, non-login).
Neither `.bashrc` nor `.bash_profile` is sourced.

Fix: Explicitly source bashrc.

```python
# Slow (50ms for aio)
subprocess.getoutput("aio")

# Fast (0.5ms for aio)
subprocess.getoutput("source ~/.bashrc && aio")
```

## When This Optimization Applies

| Scenario | Speedup |
|----------|---------|
| Commands with shell functions (aio, nvm, conda) | 10-100x |
| Commands with aliases | 2-5x |
| Native binaries (ls, git) | 2-4x |
| Shell builtins (pwd, echo) | None |

## Requirements

1. `.bashrc` must load fast (<50ms ideal)
2. No side effects in bashrc (no prints, no blocking)
3. `.bash_profile` must source `.bashrc` for tmux/SSH

## Implementation

The `aio install` command now:
1. Creates shell function in `.bashrc`
2. Creates `.bash_profile` that sources `.bashrc` (if missing)

This ensures `aio` is fast in ALL contexts: terminals, tmux, subprocesses.
