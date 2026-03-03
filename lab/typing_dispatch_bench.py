#!/usr/bin/env python3
"""Benchmark typing dispatch systems - target <1ms per keystroke"""
import time, bisect

# Copy of aio commands (unique keys only)
CMDS = ['help','update','jobs','kill','attach','cleanup','config','ls','diff','send','watch',
        'push','pull','revert','set','settings','install','uninstall','deps','prompt','gdrive',
        'add','remove','move','dash','all','backup','scan','copy','log','done','agent','tree',
        'dir','web','ssh','run','hub','daemon','ui','review','note','e','x','p','n']

# Simulated typing sessions
TYPING = ['c','cl','cle','clea','clean','cleanu','cleanup',  # cleanup
          'p','pu','pus','push',  # push
          'a','ag','age','agen','agent',  # agent
          'h','hu','hub',  # hub
          's','se','sen','send']  # send

# === Method 1: Dict with all prefixes (current aio approach) ===
def build_prefix_dict(cmds):
    d = {}
    for c in cmds:
        for i in range(1, len(c)+1):
            d.setdefault(c[:i], []).append(c)
    return d

# === Method 2: Trie ===
class Trie:
    def __init__(self):
        self.children, self.words = {}, []
    def insert(self, word):
        node = self
        for ch in word:
            node = node.children.setdefault(ch, Trie())
            node.words.append(word)
    def search(self, prefix):
        node = self
        for ch in prefix:
            if ch not in node.children: return []
            node = node.children[ch]
        return node.words

# === Method 3: Sorted list + bisect ===
def bisect_search(sorted_cmds, prefix):
    i = bisect.bisect_left(sorted_cmds, prefix)
    return [c for c in sorted_cmds[i:i+10] if c.startswith(prefix)]

# === Method 4: Simple filter ===
def filter_search(cmds, prefix):
    return [c for c in cmds if c.startswith(prefix)]

# === Benchmark ===
def bench(name, setup, search_fn, iters=10000):
    data = setup()
    start = time.perf_counter_ns()
    for _ in range(iters):
        for prefix in TYPING:
            search_fn(data, prefix)
    elapsed_ns = time.perf_counter_ns() - start
    per_key_us = elapsed_ns / (iters * len(TYPING)) / 1000
    print(f"{name:<20} {per_key_us:>8.3f} us/key  ({per_key_us/1000:.4f} ms)")
    return per_key_us

def main():
    print(f"Benchmarking {len(TYPING)} keystrokes x 10000 iterations\n")
    print(f"{'Method':<20} {'Time':>12}  {'(ms)'}")
    print("-" * 45)

    results = []
    results.append(('prefix_dict', bench("prefix_dict", lambda: build_prefix_dict(CMDS), lambda d,p: d.get(p,[]))))
    results.append(('trie', bench("trie", lambda: (t:=Trie(), [t.insert(c) for c in CMDS], t)[2], lambda t,p: t.search(p))))
    results.append(('bisect', bench("bisect", lambda: sorted(CMDS), lambda s,p: bisect_search(s,p))))
    results.append(('filter', bench("filter", lambda: CMDS, lambda c,p: filter_search(c,p))))

    print("-" * 45)
    winner = min(results, key=lambda x: x[1])
    print(f"\nFastest: {winner[0]} at {winner[1]:.3f} us ({winner[1]/1000:.4f} ms)")
    print(f"Target <1ms: {'PASS' if winner[1] < 1000 else 'FAIL'}")

if __name__ == '__main__':
    main()
