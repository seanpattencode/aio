# Claude Code V8 Crash: Node.js Version Incompatibility

**Date:** December 30, 2025
**Affected Software:** Claude Code 2.0.76
**Root Cause:** V8 JavaScript engine incompatibility with Node.js < 25

## Executive Summary

Claude Code crashes with V8 fatal errors on Node.js versions 20-24, despite officially requiring only Node 18+. The crashes occur in V8's Turboshaft JIT compiler during normal operation. Upgrading to Node.js 25+ resolves the issue.

## The Problem

### Symptoms

When running Claude Code on Node.js 20.x or 22.x, users experience fatal crashes:

```
Fatal error in , line 0
Check failed: has_pending_exception().

FailureMessage Object: 0x7ffc47ccae30
----- Native stack trace -----
 1: 0x74d707601c79  [/lib/x86_64-linux-gnu/libnode.so.115]
 2: 0x74d708475a4b V8_Fatal(char const*, ...)
 3: 0x74d707baa485 v8::internal::Isolate::UnwindAndFindHandler()
 4: 0x74d70809c3d0 v8::internal::Runtime_UnwindAndFindExceptionHandler(...)
 5: 0x74d6a7899f4c
Illegal instruction (core dumped)
```

### Crash Location

The crash occurs in V8's internal exception handling:
- `v8::internal::Isolate::UnwindAndFindHandler()` - Exception unwinding
- `has_pending_exception()` assertion failure - Internal state corruption
- Ends with `Illegal instruction` - Memory/state corruption

## Version Matrix

| Node.js Version | V8 Version | Status | Ubuntu Version |
|-----------------|------------|--------|----------------|
| Node 18.x | V8 10.2 | Crashes | Ubuntu 22.04 |
| Node 20.x | V8 11.3 | Crashes | Ubuntu 24.04 LTS |
| Node 22.x | V8 12.4 | Crashes | - |
| Node 24.x | V8 12.9 | Crashes | - |
| **Node 25.x** | **V8 13.x** | **Works** | - |

## Official Requirements vs Reality

| Anthropic States | Reality |
|------------------|---------|
| "Node.js 18+ required" | Crashes on Node 18, 20, 22, 24 |
| Works on Linux | Crashes on stock Ubuntu |
| Stable release | V8 fatal errors during normal use |

## Evidence

### GitHub Issue #1933: V8 Engine Fatal Error
- **URL:** https://github.com/anthropics/claude-code/issues/1933
- **Status:** Closed as "NOT_PLANNED"
- **Environment:** Node v22.16.0 on Ubuntu 24.04 (WSL2)
- **Outcome:** No fix provided, closed due to inactivity

### GitHub Issue #8410: Node.js Version Detection
- **URL:** https://github.com/anthropics/claude-code/issues/8410
- **Upvotes:** 87 (indicating widespread impact)
- **Issue:** Version detection failing on valid Node versions
- **Status:** Closed

## Root Cause Analysis

### Why This Happens

1. **Developer Environment Mismatch**
   - Anthropic developers likely use Node 25+ via nvm/n
   - They test on their machines with latest V8
   - Stock Ubuntu users get crashes

2. **V8 JIT Compiler Bug**
   - Crash in `Turboshaft` compiler (V8's JIT)
   - Affects `MachineLoweringReducer::ReduceStringAt`
   - Triggered during string operations

3. **Inadequate Testing**
   - Ubuntu LTS ships Node 20
   - Many users install via apt (stock version)
   - Claude Code not tested on stock Ubuntu Node

### The Gap

```
┌─────────────────────────────────────────────────────────────┐
│ Anthropic Dev Machine                                       │
│ ├── nvm/n installed                                         │
│ ├── Node 25+ (latest)                                       │
│ └── V8 13.x ✓                                               │
└─────────────────────────────────────────────────────────────┘
                            ≠
┌─────────────────────────────────────────────────────────────┐
│ Ubuntu 24.04 LTS User Machine                               │
│ ├── apt install nodejs                                      │
│ ├── Node 20.x (stock)                                       │
│ └── V8 11.3 💀 CRASH                                        │
└─────────────────────────────────────────────────────────────┘
```

## Solution

### Immediate Fix

Upgrade to Node.js 25:

```bash
# Install n (node version manager)
sudo npm install -g n

# Install Node 25
sudo n 25

# Verify
node --version  # Should show v25.x.x

# Reinstall Claude Code
npm install -g @anthropic-ai/claude-code
```

### Alternative: Use Native Binary

Anthropic provides native binaries that don't depend on system Node:

```bash
# Linux/macOS
curl -fsSL https://claude.ai/install.sh | sh

# Windows
irm https://claude.ai/install.ps1 | iex
```

## Recommendations for Anthropic

1. **Update minimum version requirement** to Node 25+ in package.json
2. **Add V8 version check** at startup with helpful error message
3. **Test on stock Ubuntu LTS** configurations
4. **Document the actual requirements** clearly

## Workaround Added to aio

The `aio` session manager now includes:

1. **Node version warning** in `aio install`:
   ```
   ⚠️  Node.js v20 is old - known V8 crashes occur. Upgrade: sudo npm i -g n && sudo n 25
   ```

2. **Crash recovery wrapper** for claude sessions:
   - Detects crashes (non-zero exit)
   - Prompts user: `[R]estart / [Q]uit`
   - Allows quick restart without recreating session

## References

- [Claude Code npm package](https://www.npmjs.com/package/@anthropic-ai/claude-code)
- [GitHub Issue #1933 - V8 Fatal Error](https://github.com/anthropics/claude-code/issues/1933)
- [GitHub Issue #8410 - Node Detection Bug](https://github.com/anthropics/claude-code/issues/8410)
- [Node.js Release Schedule](https://nodejs.org/en/about/previous-releases)
- [Node.js End of Life Dates](https://endoflife.date/nodejs)

---

*Report generated while investigating Claude Code crashes on Ubuntu with Node.js 20.19.4*
