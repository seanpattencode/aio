# aio Timing Overhead

## The Problem

Running `aio script.py` was 30ms slower than `python3 script.py`.

```
Direct python:  21ms
Via aio:        52ms
Overhead:       +31ms (148% slower)
```

## Root Cause

Python interpreter startup. Before any user code runs:
1. Python loads (~15ms)
2. aio.py imports modules (~10ms)
3. Command dispatch (~5ms)

## Solution

Shell fast-path in `~/.zshrc` / `~/.bashrc`:

```bash
[[ "$1" == *.py && -f "$1" ]] && {
    local s=$(($(date +%s%N)/1000000))
    python3 "$@"
    local r=$?
    echo "{\"cmd\":\"$1\",\"ms\":...}" >> timing.jsonl
    return $r
}
```

Runs python directly, logs timing via shell. No Python wrapper.

## Results

```
Direct python:  21ms
Shell aio:      27ms  (+6ms)
Python aio:     52ms  (+31ms)
```

5x improvement. 6ms overhead = shell function + timing log.

## Limits

| Limitation | Reason |
|------------|--------|
| zsh/bash only | Other shells don't load function |
| Interactive only | Scripts/cron use Python fallback |
| `date +%s%N` | Subprocess spawn costs ~4ms |
| macOS | May need `gdate` from coreutils |

## Path to 0ms

| Approach | Overhead | Trade-off |
|----------|----------|-----------|
| Current shell | ~6ms | Good balance |
| `$EPOCHREALTIME` | ~2ms | zsh 5.1+ only |
| No timing | 0ms | Lose metrics |
| Compiled wrapper | ~1ms | Build complexity |

## The Measurement Paradox

```
No logs → 0ms overhead → no data → no improvement
Logs    → 6ms overhead → data   → improvement possible
```

You needed timing data to discover the 30ms problem. But continuous logging costs 6ms.

## Chrome's Approach (millions of events, ~1μs each)

Chrome logs everything via `chrome://tracing` with near-zero overhead:

| Technique | How | aio equivalent |
|-----------|-----|----------------|
| **Ring buffer** | Write to pre-allocated memory, not disk | Memory array, flush on exit |
| **Thread-local** | No locks, merge later | N/A (single thread) |
| **Sampling** | Log 1% of events | `$RANDOM % 10 == 0` |
| **Compile-time off** | `#if TRACING` - zero cost when disabled | `AIO_TRACE=1` opt-in |
| **rdtsc** | CPU cycle counter, 1 instruction | `$EPOCHREALTIME` builtin |
| **Binary format** | No JSON/string formatting | Pack later, not at log time |

**Key insight:** Chrome doesn't write to disk at event time. Memory-only until export.

## Practical Strategies

| Strategy | Overhead | Use case |
|----------|----------|----------|
| Always log (current) | 6ms | Development, building habits |
| Sample 10% | ~0.6ms | Long-term monitoring |
| Log slow only (>100ms) | ~0ms typical | Regression detection |
| Benchmark mode | 0ms default | On-demand `aio --bench file.py` |
| Log first N runs | 0ms after | Initial baseline only |

## Files

- `test_aio_overhead.py` - Benchmark comparing direct/shell/python paths
- `test_startup_time.py` - Tests aio command startup times

## Running

```bash
cd feature_tests/timing
python3 test_aio_overhead.py
```
