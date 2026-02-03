# Log Compression Analysis

## Problem
Claude logs are huge (323MB for one session) but contain mostly terminal rendering overhead, not actual content. This prevents git storage (100MB limit).

## Why Logs Are So Big

Raw tmux `pipe-pane` captures everything:
- ANSI escape codes: `^[[38;2;215;119;87m` (RGB colors)
- Full-width padding: each line padded to terminal width with spaces
- Unicode box drawing: `─────` repeated 200+ times per line
- Cursor positioning sequences

**Actual text content is ~1-5% of file size.**

## Compression Results (323MB test file)

| Format | Size | Ratio | Notes |
|--------|------|-------|-------|
| Raw | 323MB | 1x | Current |
| Strip ANSI | 142MB | 2.3x | Lossy (colors gone) |
| zstd compressed | 3.4MB | **95x** | Lossless |
| Strip + compress | ~1MB | ~300x | Lossy but tiny |

## Performance (323MB file)

### Fast CPU (desktop)
| Operation | Time |
|-----------|------|
| Strip ANSI (sed) | 8s |
| Compress (zstd) | 0.07s |
| Decompress (zstd) | 0.07s |

### Weak CPU (Termux estimate)
| Operation | Time |
|-----------|------|
| Strip ANSI (sed) | 30-120s |
| Compress (zstd) | 1-2s |
| Decompress (zstd) | 1-2s |

## Tradeoffs

| Approach | Lossless | Searchable | Weak CPU | Git-able |
|----------|----------|------------|----------|----------|
| Raw | Yes | Yes | N/A | No (too big) |
| Compressed | Yes | No* | Fast | **Yes** (3.4MB) |
| Stripped | **No** | Yes | Slow | Maybe (142MB) |

*Need to decompress first to search

## Implementation Options

### Option 1: Compress on rotate (recommended)
- Keep current session raw (searchable)
- Compress when session ends or daily
- Old logs become `.log.zst` files
- Pros: Simple, lossless, git-able
- Cons: Can't grep old logs without decompress

### Option 2: Strip ANSI on save
- Modify tmux pipe-pane to filter
- `tmux pipe-pane -t $session "sed 's/\x1b\[[0-9;]*m//g' >> $logfile"`
- Pros: Searchable, smaller
- Cons: Lossy, slow on weak CPU, still 142MB

### Option 3: Dual storage
- Raw log for current session
- Extract structured metadata to JSON/SQLite (tiny, git-able)
- Compress raw log to cloud only
- Pros: Best of both worlds
- Cons: More complex

### Option 4: Do nothing (current)
- Raw logs locally
- tar.zst to GDrive via `a log sync`
- Git for small structured data only
- Pros: Simple, works
- Cons: No git history for logs

## Recommendation

**Short term:** Keep current approach (Option 4). It works.

**Medium term:** Option 1 (compress on rotate). Simple win:
```bash
# In log cleanup/rotate script
zstd --rm old_session.log  # Compress and remove original
```

**Long term:** Option 3 (dual storage) for agent manager:
- Extract session metadata to `sessions.jsonl` (git-able)
- Keep compressed raw logs in cloud for deep-dive
- Agent manager queries metadata, fetches raw on demand

## Code Sketch (Option 1)

```python
# In log.py or as cron/hub job
def rotate_logs(days=7):
    for log in Path(LOG_DIR).glob('*.log'):
        if log.stat().st_mtime < time.time() - days*86400:
            sp.run(['zstd', '--rm', '-q', str(log)])
```

## Conclusion

Compression is a **solved problem** (95x reduction, fast, lossless). The question is when/how to apply it:
- Real-time: adds complexity, minimal benefit
- On rotate: simple, effective, recommended
- On sync: already doing this with `a log sync` tar.zst

The bigger opportunity is **structured extraction** - small metadata that captures what happened without the 323MB of terminal rendering.
