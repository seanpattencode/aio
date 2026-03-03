# Termux Fork Renaming Issues

Renaming Termux's package from `com.termux` to anything else (e.g. `com.aios.a`) breaks the app. Here's why and what the options are.

## The Core Problem

Bootstrap binaries (bash, coreutils, apt, etc.) are **precompiled with hardcoded paths** like `/data/data/com.termux/files/usr/bin/sh`. These paths are baked into:
- ELF binary rpaths (cannot be sed'd without corrupting the binary)
- Shell script shebangs (`#!/data/data/com.termux/files/usr/bin/sh`)
- Library search paths in `.so` files
- Config files throughout the prefix

Changing `applicationId` changes the app's data directory from `/data/data/com.termux/` to `/data/data/com.aios.a/`, so all hardcoded paths break.

## What We Tried

1. **Change applicationId + all TERMUX_PACKAGE_NAME references** — Bootstrap extracts to wrong path, shebangs point to nonexistent `/data/data/com.termux`.
2. **Sed shebangs in scripts** — Fixes scripts but corrupts ELF binaries (sed changes binary length, breaking ELF structure).
3. **Sed only text files** — Fixes shebangs but ELF rpaths still reference `com.termux`, so shared libraries fail to load (`CANNOT LINK EXECUTABLE`).
4. **Keep TERMUX_PACKAGE_NAME as com.termux, only change applicationId** — Permission conflict (`INSTALL_FAILED_DUPLICATE_PERMISSION`) because both apps declare `com.termux.permission.RUN_COMMAND`.
5. **Also rename permissions** — Bootstrap installer looks for `/data/data/com.termux/files` which doesn't exist under the new package.
6. **Symlink /data/data/com.termux -> /data/data/com.aios.a** — Can't create without root, and stock Termux already owns that path.

## What Actually Works

### Option A: Replace stock Termux (simplest)
Uninstall stock Termux. Keep `applicationId = "com.termux"`. Sign with the debug key. Only one can exist at a time. Change only the display name via strings.xml.

### Option B: Recompile bootstrap packages
Build the entire termux-packages bootstrap with the new package name. This recompiles every binary with `/data/data/com.aios.a` paths. Requires the termux-packages build infrastructure. This is what the Termux docs recommend.

### Option C: Use `patchelf` post-install
After bootstrap extraction, use `patchelf` to rewrite rpaths in ELF binaries and sed for scripts. Complex but avoids full recompilation. Needs patchelf compiled for Android/ARM64.

## Recommendation

**Option A for now.** Uninstall stock Termux, use `com.termux` as package name, just change the display name to "aio". Get the app working first, deal with coexistence later if needed.

For coexistence long-term, Option B is the correct solution.
