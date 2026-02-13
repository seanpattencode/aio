# Future Features — from Feb 12-13 conversation

Discussed in detail, not yet implemented. Build when needed.

## 1. Seed binary distribution

Pre-built binaries for 3-4 targets so non-technical users can install with one command.

```bash
curl -L https://example.com/a | sh
```

Targets: `linux-x86_64`, `linux-arm64`, `mac-arm64`, `mac-x86_64`

The seed binary runs `a install`, installs `cc` via system package manager, then recompiles itself from source with `-march=native -O3 -flto`. After that it's self-sustaining — updates are `git pull && sh a.c`.

**Why:** Non-technical friend tested install, failed multiple times. One-command install is a real need, not premature.

**Bootstrap chain:** Pre-built binary → installs cc → recompiles from source → self-sustaining

## 2. Self-recompilation after cc install

Inside the compiled binary's install command:

```c
system("apt install -y clang || brew install llvm || pkg install -y clang");
system("sh a.c");  // recompile from source, replacing itself
```

Binary ships as lowest-common-denominator, upgrades to native-optimized on first run. Every machine gets optimal codegen for its exact CPU.

## 3. Python venv management (`sh a.c venv`)

Add a `venv)` case to the `#if 0` block:

```bash
venv)
    for PY in python3.10 python3.11 python3.12 python3; do
        command -v $PY >/dev/null && break
    done
    $PY -m venv "$D/.venv"
    "$D/.venv/bin/pip" install -q -r "$D/requirements.txt"
    ;;
```

One shared venv for all Python scripts. `sh a.c venv` once, then `$D/.venv/bin/python` forever. No activation overhead, no per-script venvs.

## 4. uv fallback for Python version pinning

When system Python is wrong version (e.g., need 3.10 for torch but system has 3.12):

```bash
venv)
    command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
    uv venv --python 3.10 "$D/.venv"
    "$D/.venv/bin/pip" install -q -r "$D/requirements.txt"
    ;;
```

uv only used once to create venv with right Python. After that, raw `$D/.venv/bin/python` — zero overhead per invocation.

**Decision:** Use system package manager first (`python3.10` direct call), only fall back to uv if version not available.

## 5. Self-contained Python scripts (polyglot)

Python equivalent of the C `#if 0` trick:

```python
#!/bin/sh
'''exec
VENV=".venv_$(basename "$0" .py)"
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q requests numpy
fi
exec "$VENV/bin/python" "$0" "$@"
'''

import requests
# actual code
```

Triple-quote is valid shell (does nothing) and valid Python (string literal, ignored). One file, self-installing, self-contained.

## 6. Cross-platform mobile app (NDK/NativeActivity)

C core + platform shims for Android/iOS:

- **Android:** NativeActivity or thin JNI shim, compile via NDK clang
- **iOS:** Same C code, compile with clang, render to CAEAGLLayer/MTKView
- **Shared:** C logic, layout engine, rendering via OpenGL ES/Vulkan

Already proven viable — NDK keyboard and launcher built previously.

**Architecture:**
```
lib/
├── arm64-v8a/libnative.so    # armv8-a baseline
├── armeabi-v7a/libnative.so  # 32-bit ARM
└── x86_64/libnative.so       # emulators
```

Android picks right .so at install time. Or ship separate APKs.

## 7. Runtime CPU feature dispatch

For performance-critical paths, detect CPU features at runtime and branch into optimized code:

```c
if (has_dotprod()) {
    use_fast_path();  // compiled with -march=armv8.2-a+dotprod
} else {
    use_slow_path();  // compiled with -march=armv8-a
}
```

Ship both as separate .so, `dlopen()` the right one based on `getauxval(AT_HWCAP)`. This is what FFmpeg and libaom do.

## 8. Profile-Guided Optimization (PGO)

```bash
# Build instrumented
clang -fprofile-generate -o myapp myapp.c
# Run on target device
./myapp typical_workload
# Rebuild with profile
clang -fprofile-use=default.profdata -o myapp myapp.c
```

Step 2 benefits from running on actual target device. Profile data is transferable — run instrumented on phone, copy `.profdata` back, rebuild on desktop.

## 9. Multi-arch APK with tuned binaries

Two binaries per ISA covers 99% of benefit:

| Binary | Target | Covers |
|--------|--------|--------|
| baseline | `armv8-a` | All ARM64 phones |
| fast | `armv8.2-a+fp16+dotprod` | 2020+ flagships |
| baseline | `x86_64` | Emulators |

Use `dlopen()` to pick at runtime, or ship separate APKs and let users choose.

## 10. `a.c` as universal runtime manager

```bash
run)
    exec "$D/.venv/bin/python" "$D/lib/$2.py" "${@:3}"
    ;;
```

`sh a.c run myscript` — a.c manages the entire lifecycle: build system, installer, env manager, runtime dispatcher. One file rules the project.

---

## Design principles (from conversation)

- **Closure:** a.c is closed over its entire environment. No free variables, no implicit dependencies.
- **AI-native architecture:** Collapse implicit environment state into explicit, self-contained, LLM-parseable artifacts. One file = one context window.
- **Source is distribution:** Don't ship binaries. Ship a.c. Every machine compiles its own. `sh a.c` works or it doesn't.
- **Make understanding unnecessary:** Don't make the system understandable, make understanding unnecessary. One file, one command, deterministic outcome.
- **Build when needed:** Don't wire up what you haven't hit yet. Each feature listed here has a trigger condition — implement when that condition is met.
