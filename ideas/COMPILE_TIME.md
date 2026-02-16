# Compile Time Is Iteration Speed

## The argument

Compile time is the dominant factor in development velocity for a
single-author CLI. Everything else (safety, ergonomics, ecosystem) is
secondary to how fast you go from edit to running code.

## Measured: 2688 lines C, aarch64 phone (Termux)

| Build | Time | Output |
|---|---|---|
| `-O0 -w` (debug) | 0.4s | fastest possible |
| `-O3 -march=native -flto` | 1.5s | full production binary, 132KB |
| `sh a.c` (checker + builder parallel) | 1.6s | all warnings + optimized binary |

Equivalent Rust project (~50 commands, same scope):
- 8,000-12,000 lines (3-4x verbosity for systems glue)
- 30-90s first compile (deps, proc macros, LLVM monomorphization)
- 5-15s incremental (linker, codegen)

## Iteration loop comparison

C:   edit → 1.5s → test → edit → 1.5s → test
Rust: edit → 15s  → test → edit → 15s  → test

10x slower feedback. Over a day: 200 iterations vs 20.
Over a week: fundamentally different code — you try more things,
test more edges, refactor more freely when the build is instant.

## -march=native: the quiet win

One flag, always on, every platform. Binary is tuned for the exact CPU:
ARMv8 NEON on phone, AVX2 on x86 server, whatever the hardware has.

Rust equivalent: `RUSTFLAGS="-C target-cpu=native"` which:
- Most people don't know or set
- Invalidates the entire cargo cache
- Not portable across machines in CI
- Most Rust binaries ship as generic x86-64 baseline

C gets this for free.

## Safety gap is smaller than people think

`-Weverything -Werror` + hardening flags already cover:
- Uninitialized memory (`-ftrivial-auto-var-init=zero`)
- Buffer overflows (`-fstack-protector-strong`, `FORTIFY_SOURCE=3`)
- Type mismatches (all implicit conversions are errors)
- Control flow integrity (`-fsanitize=cfi`, `-fcf-protection=full`)
- Stack attacks (`-fsanitize=safe-stack`, `-fstack-clash-protection`)

Rust's unique advantage (compile-time lifetime tracking, data race
prevention) matters for multi-team concurrent systems. For a
single-threaded single-author CLI: the flags cover everything.

People move to Rust to get safety they could already have with flags.
The flags are opt-in, which doesn't scale to teams — but for one
person who controls the build, opt-in is fine.

## Decision

C + flags. 1.5s builds on a phone. -march=native everywhere.
The compile time advantage compounds into better code through
faster iteration, not just faster builds.
