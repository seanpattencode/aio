# Shell Method Benchmark Results

## Key Finding

**`source ~/.bashrc &&` before commands provides 100x+ speedup for `aio`**

## Subprocess Benchmarks

| Method | ls (ms) | aio (ms) | aio Speedup |
|--------|---------|----------|-------------|
| `direct` (default) | 2.38 | 49.77 | baseline |
| `source ~/.bashrc &&` | 0.52 | **0.44** | **113x** |
| `bash -i -c` | 2.74 | 3.44 | 14x |

## tmux Context Benchmarks

| Method | ls (ms) | aio (ms) | aio Speedup |
|--------|---------|----------|-------------|
| `direct` | 4.00 | 55.00 | baseline |
| `source ~/.bashrc &&` | 4.00 | **4.00** | **14x** |
| `bash -i -c` | 4.00 | 6.00 | 9x |

## Web UI Candidates (native subprocess)

| Candidate | ls (ms) | aio (ms) |
|-----------|---------|----------|
| fastapi-query | 3.44 | 49.38 |
| flask-form | 3.91 | 50.33 |
| flask-template | 3.77 | 51.12 |

All candidates use `subprocess.getoutput()` without bashrc sourcing = **~50ms for aio**

## Analysis

### Why `source` is fastest (0.44ms for aio)

```python
subprocess.getoutput("source ~/.bashrc && aio")
```

1. Sources bashrc (~1ms) - loads `aio()` shell function
2. Shell function does `cat ~/.local/share/aios/help_cache.txt`
3. No Python interpreter startup (saves 50ms)

### Why `bash -i` is slower (3.44ms for aio)

```python
subprocess.getoutput("bash -i -c 'aio'")
```

1. Starts interactive bash (more initialization)
2. Sources bashrc
3. Runs shell function
4. Extra TTY setup overhead

### Why web candidates are slow (~50ms for aio)

```python
# Candidates use:
subprocess.getoutput("aio")  # No bashrc = no shell function = Python every time
```

## Recommendations

### For Web UI Candidates

Change from:
```python
subprocess.getoutput(cmd)
```

To:
```python
subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {cmd}")
```

**Expected improvement: 50ms → 0.5ms for aio (100x faster)**

### For General Subprocess Usage

| Scenario | Best Method |
|----------|-------------|
| Commands with shell functions (aio, nvm, conda) | `source ~/.bashrc &&` |
| Native binaries (ls, git) | Either works, source slightly faster |
| Many commands in sequence | Persistent shell process |

## Conclusion

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| `aio` subprocess | 50ms | 0.5ms | **100x** |
| `aio` in tmux | 55ms | 4ms | **14x** |
| `ls` subprocess | 2.4ms | 0.5ms | **5x** |
