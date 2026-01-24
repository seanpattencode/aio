# Multi-Device DB Sync Architecture

## Current System
- Single `aio.db` synced via git
- `git reset --hard` on pull (last-write-wins)
- Device-specific rows saved/restored around sync
- Works but loses data on concurrent edits

## Proposed: Per-Device Views

### Structure
```
~/.local/share/aios/
├── db_ubuntuSSD4Tb.db    # desktop's view
├── db_Pixel-10-Pro.db    # phone's view
├── db_HSU.db             # other device's view
├── db_agent_xyz.db       # AI agent's view
└── aio.db                # merged central view
```

### Sync Flow
1. Copy local state to `db_<DEVICE_ID>.db`
2. Merge all device dbs into `aio.db`
3. Commit all files
4. Push to git

### Merge Strategies by Table
| Table | Strategy |
|-------|----------|
| notes | Union, dedupe by content hash |
| hub_jobs | Device-specific, no merge needed |
| projects | Device-specific paths, no merge |
| settings | Latest timestamp wins |
| apps | Device-specific, no merge |

### Benefits
- **Debuggable**: see what each device thinks
- **Recoverable**: rebuild from any device's view
- **Agent-safe**: AI agents get isolated files, auditable
- **Git history**: per-device commits, not just per-sync
- **Diffable**: compare device views directly

### Comparison
```bash
# See differences between devices
sqlite3 db_phone.db .dump | diff - <(sqlite3 db_desktop.db .dump)
```

### Why Not Branches?
Files are easier to query simultaneously. Branches require checkout to inspect.

### Tradeoffs
- Storage: N devices = N+1 db files
- Complexity: merge logic needed
- Git size: more files to track

### Implementation Notes
- Basically poor man's CRDT with git as transport
- Each device db is that device's "event log"
- Central db is the "projection"
- Agents should probably commit to their own file, reviewed before merge to central
