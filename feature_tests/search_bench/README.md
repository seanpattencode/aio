# Search Method Benchmarks

Comparison of filename and content search methods.

## Precompute Search Leaderboard (10K URLs)

**Winner: precompute_py.py** - 14,454x faster than fzf

| Rank | Implementation | LOC | Avg (µs) | vs fzf | Notes |
|------|----------------|----:|----------|--------|-------|
| 🥇 | precompute_py.py | 81 | 0.4 | **14,454x** | char + prefix index |
| 🥈 | nano_precompute.py | 6 | 36 | **142x** | best for 2+ char queries |
| 🥉 | pico_precompute.py | 3 | 36 | **142x** | minimal, case-sensitive |
| 4 | fzf --filter | - | 5,100 | 1x | process spawn overhead |

### Run Benchmark
```bash
python3 bench_python_only.py
```

### Key Insight
- Single-char 'c': full=0.7µs vs nano=216µs (char index wins)
- Multi-char 'chromium': nano=0.26µs vs full=0.30µs (simpler wins)

---

## Results (10k files, 1M words)

### Filename Search

| Method | Time | Notes |
|--------|------|-------|
| bash glob `*5000*` | 2ms | Fastest, shell built-in |
| C readdir+strstr | 2ms | Minimal syscalls |
| find | 4ms | Standard, recursive |
| ls \| grep | 7ms | Two processes |
| Python scandir | 9ms | +8ms startup |
| Python listdir | 11ms | +8ms startup |

### Content Search

| Method | Time | Notes |
|--------|------|-------|
| SQLite FTS5 | 0.1ms | Pre-indexed full-text |
| ripgrep | 11ms | Parallel, no index |
| grep -r | 23ms | Single-threaded |
| Python read all | 63ms | Slow |
| SQLite LIKE | 298ms | Full scan, never use |

## Methods Explained

### Filename Search

**bash glob** - Shell expands `*pattern*` directly via kernel `getdents`. No process spawn.

**C readdir** - Direct `opendir`/`readdir` syscalls + `strstr`. What `ls` does internally.

**find** - Recursive walker using `openat`/`getdents`. Optimized C, handles deep trees.

**ls | grep** - Two processes + pipe overhead.

**os.scandir** - Python wrapper for `readdir`. Returns `DirEntry` with cached stat.

**os.listdir** - Returns filename list, then filter in Python.

### Content Search

**SQLite FTS5** - Full-text search index. Fastest if data already in SQLite.

**ripgrep** - Rust, parallel file reader, regex. Best for ad-hoc search.

**grep -r** - Standard but single-threaded.

**SQLite LIKE** - `%pattern%` can't use B-tree index. Always full scan.

## When to Use What

| Use case | Best method |
|----------|-------------|
| Single dir filename | bash glob |
| Recursive filename | find |
| Respect .gitignore | fd or rg --files |
| Pre-indexed system | locate |
| Content in SQLite | FTS5 |
| Ad-hoc content search | ripgrep |
| Embedded Python | os.scandir |

## Run

```bash
python3 bench.py
```
