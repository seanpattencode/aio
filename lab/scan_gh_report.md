# aio scan gh - Feature Report

## Changes Made

### 1. Bug Fix: Local Scan Never Found Repos
- **Issue**: `'/.' not in str(p)` checked the `.git` path which always contains `/.git`
- **Fix**: Changed to `'/.' not in str(p.parent)` to check parent directory
- **Line**: 38

### 2. GitHub Option in Local Scan
- Added `gh` to prompt: `Add (#,#-#,all,gh,q):`
- Typing `gh` switches to GitHub clone mode
- **Lines**: 37, 39

### 3. Search by Name Argument
- `aio scan gh test` filters repos containing "test"
- Partial match, case-insensitive
- **Line**: 21

### 4. Interactive Search
- Type `/pattern` at prompt to filter displayed repos
- Re-indexes from 0 after filtering
- **Line**: 29

### 5. Pagination (10 at a time)
- Shows 10 repos per page
- `m` = show next 10
- **Lines**: 23-30

### 6. Help Text
- Shows `[N repos] /search m=more` at bottom
- `m=more` only shown when more pages exist
- **Line**: 26

### 7. Removed Unused Alias
- Removed `'github'` as alias for `'gh'` to save tokens
- **Line**: 7

## Token/Line Count
```
scan.py: +18/-17 lines (+1 net), +87 tokens
```

## Cache Issue Discovered
Python bytecode cache (`.pyc` in `__pycache__`) can cause stale code to run.

**Fix**: Clear cache after edits:
```bash
find ~/projects/aio -name '__pycache__' -exec rm -rf {} +
```

Or use `hash -r` if bash command cache is suspect.

## Usage Examples
```bash
aio scan gh              # list GitHub repos (10 at a time)
aio scan gh test         # search for repos containing "test"
aio scan                 # local scan, type 'gh' to switch to GitHub
```

Interactive:
```
  0. repo-name               2026-01-27
  ...
  9. another-repo            2026-01-26
  [97 repos] /search m=more

Clone (#,#-#,all,q): /aio      # filters to repos with "aio"
Clone (#,#-#,all,q): m         # show next 10
Clone (#,#-#,all,q): 0         # clone repo 0
Clone (#,#-#,all,q): 0-3       # clone repos 0,1,2,3
Clone (#,#-#,all,q): all       # clone all filtered repos
```
