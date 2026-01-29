# AIO Sync Architecture

## Current State (2026-01-29)

### Source of Truth: Local Folder
```
~/gdrive/a/
  notes/
    {timestamp}_{id}.md    ← note content
    {timestamp}_{id}.ack   ← marks note as done
  hub/                     ← (future: scheduled jobs)
  .git/                    ← git repo for sync
```

### Sync Targets
```
1. GitHub: github.com/seanpattencode/aio-data
   - Syncs ~/gdrive/a via git push/pull
   - Provides history, versioning, conflict-free merge

2. GDrive (aio-gdrive, aio-gdrive2)
   - Currently syncs ~/.local/share/a (old system)
   - TODO: Sync ~/gdrive/a/notes as source of truth folder

3. Local Cache
   - ~/.local/share/a/aio.db (SQLite, rebuilt from folder)
```

### Key Design: Append-Only Files = Zero Conflicts
- Every note is a new file: `{timestamp}_{id}.md`
- Marking done creates new file: `{timestamp}_{id}.ack`
- Files are NEVER edited, only created
- Git merges trivially (different files = no conflict)

### Code Structure
```
a_cmd/sync.py (46 lines) - Core sync logic
  - init()        → setup folders
  - pull()        → git fetch/pull, rebuild cache
  - push(msg)     → git add/commit/push
  - rebuild()     → scan folder → rebuild DB cache
  - note_add(txt) → create .md file, update cache, push
  - note_ack(id)  → create .ack file, update cache, push
  - note_list()   → query cache (fast)

a_cmd/note.py (19 lines) - Note UI
  - Uses sync.py functions
  - Interactive mode for browsing/acking

a_cmd/backup.py (39 lines) - Status display
  - Shows folder stats, git status, gdrive status
```

## Migration Done

### From Old System (events.jsonl)
```
OLD: events.jsonl → replay_events() → aio.db
     ~154 lines, complex merge logic, sync bugs

NEW: folder/files → rebuild() → aio.db
     ~65 lines, zero conflicts, simple
```

### Data Migrated
- 341 notes exported to individual .md files
- 38 acks exported to .ack files
- Git repo initialized at ~/gdrive/a
- Pushed to github.com/seanpattencode/aio-data

## Testing Done

1. ✓ `a n "text"` - creates file, updates cache, pushes to github
2. ✓ `a n` - lists notes from cache
3. ✓ `a backup` - shows folder stats and sync status
4. ✓ rebuild() - scans 346 files in <100ms
5. ✓ Git push/pull working

## TODO

### Immediate
- [ ] Sync ~/gdrive/a to gdrive folder (not just github)
- [ ] Get clickable gdrive URL for source of truth folder
- [ ] Test pull on HSU (second device)

### Future
- [ ] Hub jobs migration to folder format
- [ ] Projects list migration
- [ ] Auto-sync on startup (check github for changes)
- [ ] Mobile access via gdrive app

## Architecture Principles

1. **Folder = Source of Truth**
   - Not a database, not a log file
   - Human-readable files anyone can edit
   - Compatible with any sync tool (gdrive, dropbox, icloud)

2. **Append-Only = No Conflicts**
   - Never edit files, only create
   - Git auto-merges different files
   - Timestamps provide ordering

3. **Local DB = Speed Cache**
   - SQLite for fast queries
   - Rebuilt from folder on sync
   - Can be deleted and rebuilt anytime

4. **Git = History + Sync**
   - Wraps the folder
   - Provides versioning (can revert)
   - GitHub = always-online sync point
