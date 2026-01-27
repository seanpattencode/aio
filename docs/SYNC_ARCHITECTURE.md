# Sync Architecture Requirements

## Problem Statement

The current `db_sync()` implementation syncs `aio.db` (binary SQLite) via git. This causes **corruption** when multiple devices sync simultaneously because:

1. Git cannot merge binary files
2. `git stash/pop` on binary SQLite corrupts data
3. Race conditions between concurrent `db_sync()` calls

Evidence from 2026-01-26 incident:
- 66 orphaned git stashes accumulated
- Multiple commits at same second (race condition)
- Database corruption after `git stash pop` on binary file

## Requirements

| # | Requirement | Rationale |
|---|-------------|-----------|
| 1 | **GitHub only** | No external services (no S3, no cloud databases) |
| 2 | **Git versioned** | Full history, can `git checkout` any version |
| 3 | **Single SQLite file** | `aio.db` remains source of truth for queries |
| 4 | **Append only** | Never DELETE/UPDATE, only INSERT (soft deletes) |
| 5 | **Zero merge conflicts** | Architecture must make conflicts impossible |
| 6 | **Raspberry Pi compatible** | Lightweight, runs on low-power devices |
| 7 | **No external tools** | Only `sqlite3` + `git` allowed |

## Solution: Append-Only Event Log

### Architecture

```
events.sql (text, git-synced)  <-->  aio.db (SQLite, local cache)
         |                                    |
    append-only                         rebuilt from events
    git auto-merges                     queryable via views
```

### Why Append-Only = Zero Conflicts

```
Device A appends:  INSERT INTO events VALUES('a1',...);
Device B appends:  INSERT INTO events VALUES('b1',...);

Git 3-way merge:   Both lines kept, no conflict
                   (Git only conflicts when SAME line modified differently)
```

### Schema

```sql
-- Core events table (append-only)
CREATE TABLE events (
    id TEXT PRIMARY KEY,      -- UUID, globally unique
    ts REAL NOT NULL,         -- Unix timestamp
    device TEXT NOT NULL,     -- Device that created event
    tbl TEXT NOT NULL,        -- Target table name
    op TEXT NOT NULL,         -- "add" or "archive"
    data TEXT NOT NULL        -- JSON payload
);

-- Views reconstruct current state
CREATE VIEW projects_live AS
SELECT
    json_extract(data, '$.id') as id,
    json_extract(data, '$.path') as path,
    ts as created_at
FROM events
WHERE tbl = 'projects' AND op = 'add'
AND json_extract(data, '$.id') NOT IN (
    SELECT json_extract(data, '$.id')
    FROM events
    WHERE tbl = 'projects' AND op = 'archive'
);
```

### Sync Flow

```
WRITE:
    1. Generate UUID for event
    2. INSERT into events table
    3. Append INSERT statement to events.sql

PUSH:
    git add events.sql
    git commit -m "sync"
    git push

PULL:
    git pull                    # auto-merges appends
    sqlite3 aio.db < events.sql # replay all events

QUERY:
    SELECT * FROM projects_live;  # view reconstructs current state
```

### File Layout

```
~/.local/share/aios/
    events.sql      # Synced via git (append-only text)
    aio.db          # Local only (.gitignore), rebuilt from events.sql
    aio.db-wal      # Local only (.gitignore)
    aio.db-shm      # Local only (.gitignore)
```

## Migration Path

1. Add `events` table and views to schema
2. Migrate existing data to events format
3. Update all writes to emit events instead of direct INSERT/UPDATE/DELETE
4. Update `db_sync()` to sync `events.sql` only
5. Add `aio.db` to `.gitignore`

## Performance Considerations

### Incremental Replay

Don't replay all events every sync - track progress:

```sql
CREATE TABLE _sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Store: last_applied_event_id
```

```python
def replay_events():
    last = db.execute("SELECT value FROM _sync_meta WHERE key='last_event'").fetchone()
    for line in open("events.sql"):
        event_id = extract_id(line)
        if last and event_id <= last:
            continue  # skip already applied
        db.execute(line)
    db.execute("UPDATE _sync_meta SET value=? WHERE key='last_event'", (event_id,))
```

### Compaction (Future)

When events.sql grows too large:

1. Snapshot current state to `checkpoint_YYYYMMDD.sql`
2. Archive old events
3. New `events.sql` starts fresh
4. Replay = load checkpoint + replay new events

## Reference Implementations

| App | Approach | Lesson |
|-----|----------|--------|
| Chrome | Operation-based sync | Local db is cache, not synced |
| Linear | Custom sync engine | Append-only operation log |
| Notion | SQLite + server sync | SQLite caches, deltas sync |
| Kafka | Partitioned log | Append-only at massive scale |
| Git itself | Append-only commits | Objects immutable, refs point to HEAD |

## Why Not Alternatives?

| Alternative | Why Not |
|-------------|---------|
| Sync SQLite directly | Binary, can't merge, corrupts |
| cr-sqlite (CRDT) | External native dependency |
| Litestream | Requires S3, not git-only |
| Per-device databases | Can't query universal state easily |
| Server-based sync | Requires running a server |

## Decision

**Approved architecture:** Append-only event log with SQLite views

- `events.sql` = source of truth (text, git-synced, append-only)
- `aio.db` = local query cache (rebuilt from events)
- Zero merge conflicts guaranteed by append-only design

---

## Current Implementation (2026-01-26)

| Spec | Actual | Why |
|------|--------|-----|
| `events.sql` | `events.jsonl` | JSONL already existed, easier to parse |
| SQL views | `replay_events()` | Rebuilds tables directly, simpler |
| Incremental replay | Full replay | <1k events, fast enough for now |
| All tables via events | Only `notes`, `ssh` | Others are device-local, no sync needed |

**Files:**
- `~/.local/share/aios/events.jsonl` - synced (append-only)
- `~/.local/share/aios/aio.db` - local cache (.gitignore)

**Code:** `aio_cmd/_common.py` lines 413-455
- `emit_event()` - append to events.jsonl
- `replay_events()` - rebuild db from events
- `db_sync()` - git sync events.jsonl only

## Git History Restore

Since `events.jsonl` is plain text in git, full history restore is trivial:

```bash
# View history
git log --oneline events.jsonl

# See any commit's state
git show abc123:events.jsonl

# Restore to any point in time
git checkout abc123 -- events.jsonl
replay_events(['notes','ssh'])  # rebuild db

# See when each event was added
git blame events.jsonl

# Recover accidentally acked note
git revert <commit-with-ack>  # or manually remove the ack line
```

This is a direct benefit of requirement #2 (git versioned) + #4 (append-only):
- Every event ever created exists in git history
- Can recover any deleted/archived data by reverting
- Full audit trail across all devices
- No special backup system needed - git IS the backup

---

*Author: Claude + Sean*
*Date: 2026-01-26*
*Status: Implemented and tested on 3 devices*
