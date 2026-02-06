# C Migration Notes

## Benchmarks (Termux, Android phone)

| Runner | Real | User |
|---|---|---|
| C binary `./ac` | 18ms | ~0ms |
| bash `a` (cache) | 21ms | ~1ms |
| python `a.py` | 203ms | 66ms |

On i9 Ubuntu both bash and C hit ~1ms. On Termux/Android neither does yet.
These are basically doing nothing (help output) — no reason we shouldn't hit <5ms on Termux too.
"Even ls is way above 1ms. But echo here is 1ms."

## Why echo is 1ms but everything else is ~18ms+ on Termux

`echo` is a **bash builtin** — runs inside the shell process. No fork, no exec, no linker. Just `write(1, "hi\n", 3)`. 0ms.

Every external binary (ls, ac, anything) pays the Termux process launch tax:

| Step | Cost on Termux |
|---|---|
| `fork()` | ~2-5ms (Android security hooks, SELinux context copy) |
| `exec()` | ~3-5ms (load ELF, kernel setup) |
| Dynamic linker (`ld.so`) | ~3-5ms (resolve libc, libandroid, etc.) |
| Filesystem ops (`opendir`, `stat`) | ~2-5ms |
| **Total floor** | **~15-20ms** |

Proof: `/bin/echo` (external binary, does nothing but print) = 19ms. `ls` = 25ms. `./ac` = 18ms.
The actual C code runs in microseconds — the 18ms IS the fork+exec+linker floor on Android.
On i9 Ubuntu the same overhead is <1ms (no Android sandbox layer).

**This means 18ms may be close to the Termux hard floor for any external binary.**

Possible ways to beat it:
- Static linking (`-static`) to skip dynamic linker (~3-5ms saved)
- `vfork()` instead of `fork()` where safe (~1-2ms saved)
- Ultimately: can't beat Android's fork+exec cost from userspace

## The 0ms path: pure-builtin bash function

"a is bash so why's that not instant?"

Current `a` function with no args does `cat "$cache"` — but `cat` is an external binary (16ms).
Replace with `$(<file)` which is a bash builtin file read: 0ms.

| Method | Time |
|---|---|
| `cat file` (external) | 16ms |
| `echo "$(<file)"` (all builtins) | 0ms |

Same problem: `sed -n "Np" file` in the number path is external. Replace with `mapfile` or `read` loop.

**Rule: if every operation in a bash function is a builtin, it runs at echo speed (0ms).**
Builtins: `echo`, `printf`, `$(<file)`, `[[`, `read`, `mapfile`, arithmetic `$((...))`.
External (16-20ms each): `cat`, `sed`, `awk`, `grep`, `ls`, `stat`.

See: `experimental/a_fast.sh` — proof of concept, all-builtin bash function.

Proof of concept results:
| Path | Time | Method |
|---|---|---|
| `a_fast` (help) | 0ms | `$(<cache)` + `printf` |
| `a_fast /projects/a` (dir) | 0ms | `[[ -d ]]` + `printf` + `cd` |

## Don't rewrite in bash — SSH and complexity

"Will this be hell over SSH? Should I rewrite in bash instead of C?"

Bash builtins only work if the function is loaded in the current shell:
```bash
ssh phone "a"        # ❌ function not loaded, fails or calls wrong thing
ssh phone "./ac"     # ✅ C binary just works, 18ms
scp ac phone:~/      # ✅ single file, no deps (except libsqlite3)
```

Bash breaks down the moment you need sqlite, string parsing, arrays of structs, error handling.
You already have 1647 lines of working C that does all of that.

**Best of both worlds — the architecture:**
- C binary = the real tool, works over SSH, does everything
- Tiny bash wrapper in `.bashrc` = intercepts 2-3 trivial cases at 0ms locally
- Bash wrapper is <10 lines, not a maintenance burden
- Just swap `cat` for `$(<file)` in the existing function

Don't go deeper into bash. Keep C as the real implementation.

Possible Termux overhead sources for ac.c specifically:
- Android security layer (SELinux, app sandbox) adds syscall overhead
- Termux's linker/loader is slower than native Linux
- SQLite open + WAL pragma on every invocation (~5-10ms on slow flash)
- `readlink("/proc/self/exe")` + multiple `stat()` calls in init_paths
- Termux filesystem (ext4-on-fuse or sdcardfs) has higher latency than native ext4

**1ms on Termux is impossible for any external binary.** Even `int main(){return 0;}` = 12-21ms.
This is Android's fork+exec+dynamic linker tax. No optimization can fix it from userspace.
On i9 Ubuntu the same noop binary hits ~1ms — the overhead is purely Android/Termux.

**This is Android, not Termux being bad.** Termux is just a terminal emulator running normal
Linux binaries. The 15ms floor comes from:
1. **SELinux** — every `exec()` triggers mandatory access control security context check.
   Desktop Linux usually has SELinux permissive or disabled.
2. **App sandbox** — Termux runs inside an Android app container. Every syscall goes through
   extra kernel security hooks (seccomp-bpf filters) that desktop Linux doesn't have.
3. **Zygote model** — Android apps fork from a prewarmed Zygote process. Raw `fork+exec`
   (what every CLI binary does) is the slow path Android never optimized for.
4. **Filesystem** — Termux storage sits on Android's fuse/sdcardfs layer, adding overhead
   to every `open()`/`stat()`. Desktop Linux hits ext4 directly.

On a rooted device with SELinux permissive, the same binary would be faster.
Root would also enable CPU pinning (`taskset` to big core) and `performance` governor.
NDK doesn't help — same compiler, same kernel, same security layer. NDK is for building
apps inside the Android framework, not faster CLI binaries.

## Why Android is fast at everything except process spawning

"Surely many ops run in 1ms in Android — it's an existing process spawn needed right?"

Yes. The 15ms tax is specifically `fork+exec` of a **new process**. Android is fast when
you stay inside an existing process:

| Operation | Time | Why |
|---|---|---|
| Method call inside app | ~microseconds | Same process, no kernel |
| Binder IPC (cross-app) | ~0.1-0.5ms | Message passing between existing processes |
| Bash builtin | 0ms | Already-running shell process |
| `fork+exec` new binary | **15-20ms** | SELinux + sandbox + linker + scheduler |

Android apps never call `fork+exec`. They fork from Zygote (prewarmed), talk via Binder
(existing processes), run code in-process. The `fork+exec` path was never optimized because
Android never uses it.

This is why the bash builtin approach works — the bash process is already running.
`$(<file)` and `printf` execute inside that process. Same reason Android apps are fast.

Occasional 30ms spikes on ac are not GC (C has no GC) — it's CPU frequency scaling
(Android clocks down when idle), big.LITTLE scheduler migration, cold page cache,
or background Android system work.

The only way to get C-speed without the spawn tax: a long-running daemon (like Zygote).
C process stays alive, talk to it over a socket. Overkill when bash builtins cover the
fast paths already.

The real solution: 0ms bash builtin wrapper for fast paths, C binary (~15ms) for everything else.
See `experimental/docs/install_ac.sh`.

## Final verdict: ac can never hit 1ms on Termux

ac is an external binary. Any external binary on Android = 15-20ms. No fix without root.
`a` (bash function) hits 1ms because it runs inside the already-running shell process.
That's the only way to get sub-15ms on Android: stay inside an existing process.

| Command | Time | Why |
|---|---|---|
| `a` (bash function) | **1ms** | Runs inside existing bash process |
| `ac` (C binary) | **15-20ms** | fork+exec+linker, Android floor |

ac is the fallback for commands that need sqlite/real logic. The bash wrapper handles
the 3 most-typed fast paths (help, number, dir) at 1ms. This is the ceiling on Android.

The bash wrapper is worth it: `a` (no args) is the single most common invocation.
For everything else, 15ms via C is already 13x faster than 200ms via Python.

C binary: `experimental/ac.c` (1647 lines, 73K binary)
Compile: `gcc -O2 -Wall -Wextra -Wno-unused-parameter -I$HOME/micromamba/include -L$HOME/micromamba/lib -o ac ac.c -lsqlite3`
Compile time: ~0.35s user (warm cache)

## Current Architecture

- Bash shell function in `~/.bashrc` intercepts `a` command
- Fast paths (no args, number, tasks) handled in pure bash via cache files
- Falls back to `python a.py` for complex commands
- Cache files: `help_cache.txt`, `projects.txt`, `i_cache.txt`, `t_cache`
- Python `sess.py` orchestrates tmux sessions for LLM CLIs (claude, codex, gemini)
- Only `ask.py` makes a direct API call (anthropic SDK)

## Problem: "bash is a pain to develop and debug and ssh complexity"

- Quoting hell, no real data structures, debugging is `set -x`
- SSH between devices: different shells, PATHs, bash versions
- The bash cache layer is clever but fragile
- C binary already achieves 18ms without any bash cache

## C-to-Python Interop Options

### 1. subprocess (current approach)
```c
pcmd("python script.py --args", out, sizeof(out));
```
- ~200ms overhead every call (Python interpreter startup)
- Simplest, zero coupling
- Fine when downstream is network-bound anyway

### 2. Embedded Python (libpython)
```c
#include <Python.h>
Py_Initialize();  // ~100ms once
PyRun_SimpleString("...");  // near-instant after
```
- First call ~100ms, subsequent ~0ms (amortized)
- Links against libpython (~4MB), inherits GIL, crash modes
- Build complexity: `python3-config --cflags --ldflags --embed`
- "Embedding links your 73K binary against all of libpython"

### 3. ctypes (call C from Python)
```python
import ctypes
lib = ctypes.CDLL('./libac.so')
lib.my_func.restype = ctypes.c_int
```
- ~1-2us per call overhead
- Compile with `-shared -fPIC -o libac.so ac.c`
- Useful if Python remains the entry point calling C for speed

### 4. Prewarmed Python Worker

"A single long-lived Python process is cheaper than spawning one each time"

```c
// C side: connect to /tmp/a_py.sock, send command, read response
// if connect fails, spawn worker, retry
```

```python
# worker.py - prewarmed, imports already loaded
import sys, anthropic  # pay import cost once
for line in sys.stdin:
    cmd, *args = line.strip().split('\t')
    print(result, flush=True)
```

- Auto-starts on first need, stays warm, dies on idle timeout
- No bash, no shell functions, no cache files
- C binary as sole entry point, Python sidecar for SDK-dependent commands
- Unix socket: simple, fast, no shell overhead

**Previous attempt had issues**: "I tried prewarming before, it caused issues breaking stuff, slowing it down."

Known pitfalls of prewarmed workers and how to do it better:
- **Stale state**: worker caches module state at import time. If config/DB changes, worker has stale data.
  Fix: don't cache app state in the worker, re-read DB/config per request (sqlite is fast)
- **Zombie process**: worker dies silently, C side hangs waiting on dead socket.
  Fix: non-blocking connect with timeout, auto-respawn on failure, PID file with liveness check
- **Resource leak**: long-lived Python process grows memory over time.
  Fix: idle timeout (kill after 60s of no requests), or max-requests counter then restart
- **Startup race**: C spawns worker, immediately connects before it's ready.
  Fix: worker creates socket THEN signals ready (write PID file after bind), C retries with backoff
- **Bash prewarming was the problem, not the concept**: shell functions intercepting commands + background processes + cache files = fragile. A unix socket between C and Python is much cleaner — single IPC mechanism, no shell layer, no cache files to invalidate

## Data Passing (C to/from Python)

| Method | Use case |
|---|---|
| stdout/pcmd() | Simple string results |
| Exit code | Boolean/status (0-255) |
| Shared SQLite (`aio.db`) | Structured data, both sides already connected |
| Unix socket | Prewarmed worker IPC |

"The SQLite DB you already share is the cleanest answer. No parsing stdout, no temp files, both sides already have the connection."

## Which Commands Need Python

Most commands are pure process orchestration (tmux, exec, file I/O, sqlite) — already done in C.

Python-dependent:
- `ask.py` — anthropic SDK (`anthropic.Anthropic().messages.create()`)
- Any future direct LLM API calls
- Could be replaced with libcurl POST to `api.anthropic.com` (~20 lines of C)

## Recommended Migration Path

1. C binary replaces bash cache AND python entry point (done: `experimental/ac.c`)
2. Kill bash shell function entirely — just symlink `ac` to `~/.local/bin/a`
3. For Python-dependent commands: prewarmed unix socket worker OR just subprocess (200ms is noise next to API latency)
4. Long term: libcurl for API calls, eliminate Python dependency entirely

## Final Benchmarks After Optimization

Termux hard floor for any external binary: ~15-20ms (fork+exec+dynamic linker on Android).
Cannot be beaten from userspace. Even `int main(){return 0;}` takes 12-21ms.
ac binary itself runs at ~15ms, not 1ms — that's the floor, not a bug.

| Path | Old (python) | New | Method |
|---|---|---|---|
| `a` (help) | 203ms | **0ms** | bash builtin `$(<file)` |
| `a 0` (project) | 203ms | **0ms** | bash builtin `mapfile` |
| `a /dir` (cd) | 203ms | **0ms** | bash builtin `[[ -d ]]` |
| `a <cmd>` | 203ms | **~18ms** | C binary |

Install: `bash experimental/install_ac.sh`

## Key Files

- `experimental/ac.c` — C monolith (1647 lines)
- `a.py` — Python entry point
- `a_cmd/sess.py` — session orchestrator (tmux)
- `a_cmd/ask.py` — direct anthropic API call
- `a_cmd/_common.py` — shared utilities, DB init
- `install.sh` — installs bash shell function (old, uses cat/sed)
- `experimental/install_ac.sh` — new installer: compiles C binary + 0ms bash wrapper
- `experimental/ac_bench.c` — syscall-level profiler for Termux overhead
- `experimental/a_fast.sh` — proof of concept all-builtin bash function
