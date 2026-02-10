# cmd_ssh issues

## 1. Duplicate hosts from sync conflict files
`listdir` loads all `.txt` files in `ssh/` dir. Sync creates timestamped
duplicates (e.g. `hsu_20260204T...txt`, `hsu_20260205T...txt`). Both have
`Name: hsu` so the host appears multiple times in the list and `a ssh`
output shows duplicates.

**Fix**: Deduplicate by Name when loading — skip if name already seen.

## 2. `a ssh all` command quoting is broken
Line 1653: `'bash -ic %s'` — the cmd is not quoted, so multi-word commands
break. E.g. `a ssh all "ls -la"` produces `bash -ic ls -la` which only
runs `ls`.

**Fix**: Wrap cmd in single quotes with proper escaping, matching the
pattern used in the single-host run path (line 1676).

## 3. `a ssh <n> <cmd>` remote exec captures stderr but uses -tt
Lines 1676-1678: Uses `-tt` (force PTY) with `2>&1` capture. PTY merges
stdout/stderr anyway and adds carriage returns to output, making `pcmd`
capture unreliable for scripted use.

**Fix**: Drop `-tt` for remote command execution (keep it only for
interactive connect).

## 4. `a ssh rm` silently ignores missing host
Line 1635-1641: `atoi(argv[3])` returns 0 for non-numeric input, which
silently deletes host 0. No feedback if index is out of range.

**Fix**: Validate input is numeric and print error on bad index.

# cmd_update issues

## 5. Self-build only runs when behind
Line 1819: `make -C` is inside the `else` (behind) branch. If the user
edits `a.c` locally or the previous build failed, `a update` won't
rebuild since it reports "Up to date".

**Fix**: Move build step after the if/else block so it always runs.

## 6. `make` dependency for self-build
Line 1819: Uses `make` which may not be installed (e.g. minimal server,
container, fresh Termux). Build silently fails with `2>/dev/null`.

**Fix**: Fall back to direct `clang`/`gcc` invocation when `make` is
unavailable:
```
cd SDIR && { command -v clang && clang -O2 -o a a.c -lsqlite3 || gcc -O2 -o a a.c -lsqlite3; }
```

## 7. No build success/failure feedback
Line 1819: `(void)!system(c)` discards the return code. User gets no
indication whether the build succeeded or failed.

**Fix**: Check return code and print status.
