# Multithreading Analysis

## Status: Not needed. Fork is the right primitive.

## Why threads are non-trivial

All shared data is mutable static arrays with no synchronization:

| Global | Writers | Problem |
|---|---|---|
| `PJ[MP]`/`NPJ` | `load_proj` | Concurrent load + read corrupts index |
| `SE[MS]`/`NSE` | `load_sess` | Same |
| `CF[64]`/`NCF` | `load_cfg`, `cfset` | Same, plus write-write race in cfset |
| `AP[MA]`/`NAP` | `load_apps` | Same |
| `gnp[]`,`gnt[]`,`T[]` | note.c | 384KB static, shared across calls |
| `HJ[MJ]`/`NJ` | hub.c | Same pattern |

Path globals (`HOME`, `SROOT`, `DDIR`, etc.) are write-once at init — safe.
Data arrays are loaded on-demand and mutated — unsafe under threads.

Threading would require one of:
- **Mutex per array** (~80 lines, deadlock-prone)
- **Per-thread ctx_t** (~100 lines, the "proper" refactor)
- **Atomic swap** (load into local, pointer swap — cleanest, biggest rewrite)

## Why threads aren't needed

Program lifecycle is: `init → parse → load → one command → exit` in ~30ms.

The "slow" parts are external processes (tmux/git/ssh via `popen`/`system`).
These already run in separate processes. Nothing in the C code is CPU-bound.

## Fork is the right answer

`fork()` gives parallelism without touching a line:
- Each child gets its own copy of all globals — no sharing, no locking
- Already used: `alog` (async write), `push.ok` check (background git)
- Correct for fire-and-forget work in a short-lived CLI
- Zero synchronization code needed

If concurrent command execution is ever wanted, `fork()` per command with
a shared result pipe is simpler and safer than threading this architecture.

## Decision

Label: not essential to fix. The global/static design is correct for a
single-threaded CLI dispatcher. Fork covers all parallelism needs.
Refactoring for threads would add complexity for zero user-visible benefit.
