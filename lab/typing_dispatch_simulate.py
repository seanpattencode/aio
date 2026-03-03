#!/usr/bin/env python3
"""Simulate typing session and show per-keystroke latency"""
import time

CMDS = ['help','update','jobs','kill','attach','cleanup','config','ls','diff','send','watch',
        'push','pull','revert','set','settings','install','uninstall','deps','prompt','gdrive',
        'add','remove','move','dash','all','backup','scan','copy','log','done','agent','tree',
        'dir','web','ssh','run','hub','daemon','ui','review','note','e','x','p','n']

# Build prefix dict
PREFIX = {}
for c in CMDS:
    for i in range(1, len(c)+1):
        PREFIX.setdefault(c[:i], []).append(c)

def simulate_typing(word):
    """Simulate typing a word char by char, return latencies"""
    buf, latencies = "", []
    for ch in word:
        buf += ch
        start = time.perf_counter_ns()
        matches = PREFIX.get(buf, [])[:5]
        elapsed_us = (time.perf_counter_ns() - start) / 1000
        latencies.append((buf, matches, elapsed_us))
    return latencies

def main():
    sessions = ['cleanup', 'push', 'agent', 'hub', 'config', 'install', 'uninstall']

    print("Simulated Typing Sessions")
    print("=" * 60)

    all_latencies = []
    for word in sessions:
        print(f"\nTyping: '{word}'")
        print(f"{'Input':<12} {'Suggestions':<30} {'Latency':>10}")
        print("-" * 60)
        for buf, matches, us in simulate_typing(word):
            all_latencies.append(us)
            m_str = ", ".join(matches[:3]) + ("..." if len(matches) > 3 else "")
            status = "OK" if us < 1000 else "SLOW"
            print(f"{buf:<12} {m_str:<30} {us:>8.2f} us {status}")

    print("\n" + "=" * 60)
    print(f"Total keystrokes: {len(all_latencies)}")
    print(f"Avg latency:      {sum(all_latencies)/len(all_latencies):.2f} us")
    print(f"Max latency:      {max(all_latencies):.2f} us")
    print(f"Target <1ms:      {'PASS' if max(all_latencies) < 1000 else 'FAIL'} (max {max(all_latencies)/1000:.4f} ms)")

if __name__ == '__main__':
    main()
