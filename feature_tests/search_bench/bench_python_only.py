#!/usr/bin/env python3
"""
Benchmark Python precompute implementations + fzf comparison.
"""

import time
import os
import subprocess
from collections import defaultdict

SEARCH_DIR = os.path.dirname(os.path.abspath(__file__))

# Test data - 10K URLs with "chromium" targets
URLS = [f"https://example{i}.com/path/page{i}" for i in range(5000)]
URLS.append("https://chromium.org/important")
URLS.append("https://github.com/chromium/chromium")
URLS.extend([f"https://other{i}.net/path" for i in range(5000)])
URL_DATA = "\n".join(URLS)

SEARCH_TERMS = ["c", "ch", "chr", "chro", "chrom", "chromium"]
ITERS = 1000
FZF_ITERS = 20

# ============== IMPLEMENTATIONS ==============

# 1. pico (3 lines) - case sensitive bigram
def build_pico():
    x = {}
    for i, u in enumerate(URLS):
        for j in range(len(u) - 1):
            x.setdefault(u[j:j+2], []).append(i)
    return x

def search_pico(q, ix):
    return [URLS[i] for i in ix.get(q[:2], range(len(URLS))) if q in URLS[i]][:9]

# 2. nano (6 lines) - same as pico, cleaner
def build_nano():
    ix = {}
    for i, u in enumerate(URLS):
        for j in range(len(u) - 1):
            ix.setdefault(u[j:j+2], []).append(i)
    return ix

def search_nano(q, ix):
    return [URLS[i] for i in ix.get(q[:2], range(len(URLS))) if q in URLS[i]][:5]

# 3. tiny (10 lines) - case insensitive, alpha only
def build_tiny():
    ix = defaultdict(list)
    for i, u in enumerate(URLS):
        for j in range(len(u) - 1):
            if u[j:j+2].isalpha():
                ix[u[j:j+2].lower()].append(i)
    return dict(ix)

def search_tiny(q, ix):
    c = ix.get(q[:2].lower(), []) if len(q) > 1 else range(len(URLS))
    return [URLS[i] for i in c if q.lower() in URLS[i].lower()][:8]

# 4. mini (35 lines) - case insensitive, alnum
def build_mini():
    ix = defaultdict(list)
    for i, u in enumerate(URLS):
        for j in range(len(u) - 1):
            p = u[j:j+2].lower()
            if p.isalnum():
                ix[p].append(i)
    return dict(ix)

def search_mini(q, ix):
    if len(q) < 2:
        return [URLS[i] for i, u in enumerate(URLS) if q.lower() in u.lower()][:10]
    return [URLS[i] for i in ix.get(q[:2].lower(), []) if q.lower() in URLS[i].lower()][:10]

# 5. full (81 lines) - char + prefix index
def build_full():
    char_index = defaultdict(set)
    prefix_index = {}
    for i, item in enumerate(URLS):
        item_lower = item.lower()
        seen_chars = set()
        seen_prefixes = set()
        for j, c in enumerate(item_lower):
            if c.isalnum():
                if c not in seen_chars:
                    char_index[c].add(i)
                    seen_chars.add(c)
                if j + 1 < len(item_lower):
                    prefix = item_lower[j:j+2]
                    if prefix not in seen_prefixes and prefix[1].isalnum():
                        if prefix not in prefix_index:
                            prefix_index[prefix] = set()
                        prefix_index[prefix].add(i)
                        seen_prefixes.add(prefix)
    return {k: sorted(v) for k, v in char_index.items()}, {k: sorted(v) for k, v in prefix_index.items()}

def search_full(q, ctx):
    char_index, prefix_index = ctx
    if not q:
        return URLS[:10]
    q = q.lower()
    if len(q) >= 2 and q[:2] in prefix_index:
        candidates = prefix_index[q[:2]]
    elif q[0] in char_index:
        candidates = char_index[q[0]]
    else:
        return []
    results = []
    for i in candidates:
        if q in URLS[i].lower():
            results.append(URLS[i])
            if len(results) >= 10:
                break
    return results

# 6. Linear baseline
def search_linear(q, _):
    return [u for u in URLS if q.lower() in u.lower()][:10]

# ============== FZF ==============

def bench_fzf():
    times = {}
    for term in SEARCH_TERMS:
        elapsed_list = []
        for _ in range(FZF_ITERS):
            start = time.perf_counter()
            subprocess.run(["fzf", "--filter", term], input=URL_DATA,
                         capture_output=True, text=True)
            elapsed_list.append(time.perf_counter() - start)
        times[term] = (sum(elapsed_list) / len(elapsed_list)) * 1_000_000
    return times

# ============== BENCHMARK ==============

def bench(search_fn, index):
    times = {}
    for term in SEARCH_TERMS:
        start = time.perf_counter_ns()
        for _ in range(ITERS):
            search_fn(term, index)
        times[term] = (time.perf_counter_ns() - start) / ITERS / 1000
    return times

def get_loc(filename):
    path = os.path.join(SEARCH_DIR, filename)
    if os.path.exists(path):
        with open(path) as f:
            return len([l for l in f.readlines() if l.strip() and not l.strip().startswith('#')])
    return 0

def main():
    print("=" * 80)
    print("PYTHON PRECOMPUTE vs FZF BENCHMARK")
    print("=" * 80)
    print(f"Data: {len(URLS):,} URLs | Python: {ITERS} iters | fzf: {FZF_ITERS} iters")
    print()

    # Build indexes
    print("Building indexes...", end=" ", flush=True)
    pico_ix = build_pico()
    nano_ix = build_nano()
    tiny_ix = build_tiny()
    mini_ix = build_mini()
    full_ix = build_full()
    print("done")

    # Verify
    print("Verifying...", end=" ", flush=True)
    for name, fn, ix in [("pico", search_pico, pico_ix), ("nano", search_nano, nano_ix),
                          ("tiny", search_tiny, tiny_ix), ("mini", search_mini, mini_ix),
                          ("full", search_full, full_ix)]:
        result = fn("chromium", ix)
        assert any("chromium" in str(r) for r in result), f"{name} failed"
    print("all pass")
    print()

    # Benchmark
    print("Benchmarking Python implementations...")
    results = []

    impls = [
        ("Linear (baseline)", None, search_linear, None),
        ("pico_precompute.py", "pico_precompute.py", search_pico, pico_ix),
        ("nano_precompute.py", "nano_precompute.py", search_nano, nano_ix),
        ("tiny_precompute.py", "tiny_precompute.py", search_tiny, tiny_ix),
        ("mini_precompute.py", "mini_precompute.py", search_mini, mini_ix),
        ("precompute_py.py", "precompute_py.py", search_full, full_ix),
    ]

    for name, filename, fn, ix in impls:
        loc = get_loc(filename) if filename else 0
        times = bench(fn, ix)
        results.append((name, loc, times))

    print("Benchmarking fzf --filter...")
    fzf_times = bench_fzf()
    results.append(("fzf --filter", 0, fzf_times))

    # ============== RESULTS ==============

    def avg_time(r):
        return sum(r[2].values()) / len(SEARCH_TERMS)

    print()
    print("### Search Latency (µs) - Lower is Better")
    print()

    header = "| Implementation | LOC |"
    for t in SEARCH_TERMS:
        header += f" '{t}' |"
    header += " **Avg** |"
    print(header)
    print("|" + "----------------|" + "----:|" + "------:|" * (len(SEARCH_TERMS) + 1))

    for name, loc, times in sorted(results, key=avg_time):
        row = f"| {name} | {loc or '-'} |"
        for term in SEARCH_TERMS:
            t = times[term]
            if t < 1:
                row += f" {t:.2f} |"
            elif t < 1000:
                row += f" {t:.0f} |"
            else:
                row += f" {t/1000:.1f}k |"
        avg = sum(times.values()) / len(SEARCH_TERMS)
        if avg < 1000:
            row += f" **{avg:.1f}** |"
        else:
            row += f" **{avg/1000:.1f}k** |"
        print(row)

    # ============== SPEEDUP ==============

    print()
    print("### Speedup vs fzf")
    print()

    fzf_avg = sum(fzf_times.values()) / len(SEARCH_TERMS)

    print("| Implementation | LOC | Avg (µs) | vs fzf |")
    print("|----------------|----:|----------|--------|")

    for name, loc, times in sorted(results[:-1], key=avg_time):  # exclude fzf
        if "baseline" in name:
            continue
        avg = sum(times.values()) / len(SEARCH_TERMS)
        speedup = fzf_avg / avg
        bar = "█" * min(int(speedup / 10), 20)
        print(f"| {name} | {loc} | {avg:.1f} | **{speedup:.0f}x** {bar} |")

    # ============== SUMMARY ==============

    print()
    print("### Summary")
    print()

    sorted_py = sorted(results[1:-1], key=avg_time)  # exclude baseline and fzf
    best = sorted_py[0]
    print(f"**Winner**: {best[0]} ({best[1]} LOC) @ {avg_time(best):.1f} µs avg")
    print(f"**vs fzf**: {fzf_avg / avg_time(best):.0f}x faster")
    print(f"**vs linear**: {avg_time(results[0]) / avg_time(best):.0f}x faster")

    # Multi-char winner
    def avg_multi(r):
        return sum(r[2][t] for t in SEARCH_TERMS if len(t) >= 2) / 5

    sorted_multi = sorted(results[1:-1], key=avg_multi)
    best_multi = sorted_multi[0]
    print()
    print(f"**Best for 2+ char queries**: {best_multi[0]} @ {avg_multi(best_multi):.2f} µs")

if __name__ == "__main__":
    main()
