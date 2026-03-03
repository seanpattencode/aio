# Extensionless Polyglot Experiments

## The Question

File extensions are a 1960s convention (CTSS, MIT). Unix never required them.
`a.c` costs 2 characters. Removing the `.c` saves those 2 chars but costs `-x c` in the compile command. Same budget, different location.

So what do you actually *gain* without an extension?

## What No Extension Enables

**Language-independent identity.** The file is not "a C program" — it's just `a`. The implementation language becomes a hidden detail. You can rewrite it in Rust, Zig, Python without renaming anything.

**Free dispatch.** The shell preamble isn't constrained to "compile C". It becomes an adapter layer:
- Try embedded binary → try compile C → try Python fallback
- The file works on machines with no compiler at all
- One URL, one `curl | sh`, every platform

**Self-bundling.** Without the `.c` promise, you can append a compiled binary into the file itself. `bundle` compiles and appends; `clean` strips it back to source. The file carries both source and binary.

**Self-modification.** An LLM can rewrite the source, recompile, and run — all within the same file. The file evolves at runtime.

## Experiments

### `../extensionless` — Self-bundling polyglot

One file, four layers: shell dispatcher, embedded binary, C source, Python fallback.

```
sh extensionless           # run (binary > compile > python)
sh extensionless bundle    # compile + append ELF binary into self
sh extensionless clean     # strip binary, back to source
```

### `polyglot` — Three languages + LLM self-modification

Runs bash, python, and C from one file. `mutate` calls Claude API to rewrite the C puts string, then recompiles and runs.

```
sh polyglot                # all three languages
sh polyglot mutate         # LLM rewrites C code, recompiles, runs
sh polyglot mutate         # each call produces different output
```

Example mutation:
```
before: puts("compiled native, no extension needed");
after:  puts("Runtime rewrites itself, dreams in bytecode");
[bash] pid=1317077 shell=5.2.37(1)-release arch=x86_64
[python] 3.13 arch=x86_64
Runtime rewrites itself, dreams in bytecode
```

## Why `a.c` Keeps the Extension

`.c` pays 2 characters in the filename where every tool reads it automatically.
`-x c` pays 2 characters in the build command where nobody sees it.

LLMs, editors, GitHub, linters all use the extension as primary language signal.
The extension is the cheapest metadata in the ecosystem.

The freedom from no extension is real but currently costs more in legibility than it saves.
The move makes sense when the file stabilizes into infrastructure nobody reads.

## Other Patterns Considered

**Generic binary + recompile**: Ship a portable binary, run immediately, recompile natively in background. Not worth it for `a` — compile time is already <1s.

**Binary shedding**: Ship fat multi-arch file, detect platform, delete unused binaries. Inverse of bundling. Not worth it at `a`'s current 16KB binary size — source distribution is smaller than any single binary.
