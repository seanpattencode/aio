#!/usr/bin/env python3
"""Benchmark fuzzy string matching methods for interactive search"""
import timeit, re

# Sample project list (realistic paths)
ITEMS = [
    "/home/user/projects/software-manager",
    "/home/user/projects/aio",
    "/home/user/projects/web-scraper",
    "/home/user/projects/data-analysis",
    "/home/user/projects/machine-learning",
    "/home/user/projects/api-gateway",
    "/home/user/projects/user-dashboard",
    "/home/user/projects/file-server",
    "/home/user/projects/software-tools",
    "/home/user/projects/soft-dev-kit",
] * 10  # 100 items

QUERIES = ["sof", "s o f", "soft", "mach", "api", "user"]

# Method 1: Simple substring (baseline)
def match_substring(items, q):
    q = q.replace(" ", "")
    return [x for x in items if q in x]

# Method 2: All chars in order (fuzzy)
def match_chars_in_order(items, q):
    q = q.replace(" ", "").lower()
    def m(s):
        s = s.lower(); i = 0
        for c in s:
            if c == q[i]: i += 1
            if i == len(q): return True
        return False
    return [x for x in items if m(x)]

# Method 3: Regex pattern (compile per query)
def match_regex(items, q):
    q = q.replace(" ", "")
    pat = re.compile('.*'.join(re.escape(c) for c in q), re.I)
    return [x for x in items if pat.search(x)]

# Method 4: Precompiled regex variant
REGEX_CACHE = {}
def match_regex_cached(items, q):
    q = q.replace(" ", "")
    if q not in REGEX_CACHE:
        REGEX_CACHE[q] = re.compile('.*'.join(re.escape(c) for c in q), re.I)
    return [x for x in items if REGEX_CACHE[q].search(x)]

# Method 5: Pure python chars in order (optimized)
def match_chars_fast(items, q):
    q = q.replace(" ", "").lower()
    r = []
    for x in items:
        xl, i = x.lower(), 0
        for c in xl:
            if c == q[i]:
                i += 1
                if i == len(q): r.append(x); break
    return r

# Method 6: Using find() for each char
def match_find(items, q):
    q = q.replace(" ", "").lower()
    r = []
    for x in items:
        xl, pos = x.lower(), 0
        ok = True
        for c in q:
            pos = xl.find(c, pos)
            if pos == -1: ok = False; break
            pos += 1
        if ok: r.append(x)
    return r

# Run benchmarks
def bench(name, fn, n=1000):
    total = 0
    for q in QUERIES:
        t = timeit.timeit(lambda: fn(ITEMS, q), number=n)
        total += t
    avg_us = (total / (len(QUERIES) * n)) * 1_000_000
    print(f"{name:30} {avg_us:8.2f} us/query")
    return avg_us

print(f"Items: {len(ITEMS)}, Queries: {QUERIES}\n")
print("=" * 50)

results = []
results.append(("substring", bench("1. substring (in)", match_substring)))
results.append(("chars_in_order", bench("2. chars_in_order (loop)", match_chars_in_order)))
results.append(("regex", bench("3. regex (compile each)", match_regex)))
results.append(("regex_cached", bench("4. regex (cached)", match_regex_cached)))
results.append(("chars_fast", bench("5. chars_fast (optimized)", match_chars_fast)))
results.append(("find", bench("6. find() sequential", match_find)))

# Test optional libraries
print("\n--- Optional Libraries ---")
try:
    from rapidfuzz import fuzz, process
    def match_rapidfuzz(items, q):
        q = q.replace(" ", "")
        return [x for x in items if fuzz.partial_ratio(q, x) > 70]
    results.append(("rapidfuzz", bench("7. rapidfuzz partial_ratio", match_rapidfuzz)))
except ImportError:
    print("7. rapidfuzz: not installed (pip install rapidfuzz)")

try:
    from thefuzz import fuzz as tfuzz
    def match_thefuzz(items, q):
        q = q.replace(" ", "")
        return [x for x in items if tfuzz.partial_ratio(q, x) > 70]
    results.append(("thefuzz", bench("8. thefuzz partial_ratio", match_thefuzz)))
except ImportError:
    print("8. thefuzz: not installed (pip install thefuzz)")

try:
    import difflib
    def match_difflib(items, q):
        q = q.replace(" ", "")
        return difflib.get_close_matches(q, items, n=len(items), cutoff=0.3)
    results.append(("difflib", bench("9. difflib get_close_matches", match_difflib)))
except Exception as e:
    print(f"9. difflib: {e}")

print("\n" + "=" * 50)
best = min(results, key=lambda x: x[1])
print(f"\nFASTEST: {best[0]} at {best[1]:.2f} us/query")

# Verify correctness
print("\nCorrectness check for 's o f':")
for name, fn in [("substring", match_substring), ("chars_fast", match_chars_fast),
                 ("find", match_find), ("regex_cached", match_regex_cached)]:
    r = fn(ITEMS[:10], "s o f")
    print(f"  {name}: {len(r)} matches - {[x.split('/')[-1] for x in r[:3]]}")
