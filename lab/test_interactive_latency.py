#!/usr/bin/env python3
"""Test latency of the actual i.py PREFIX lookups"""
import time
import sys
sys.path.insert(0, '.')
from aio_cmd.i import PREFIX, CMDS

def test_latency():
    typing_sessions = [
        'cleanup', 'push', 'agent', 'hub', 'config',
        'install', 'uninstall', 'remove', 'watch', 'diff'
    ]

    all_latencies = []
    for word in typing_sessions:
        buf = ""
        for ch in word:
            buf += ch
            start = time.perf_counter_ns()
            matches = PREFIX.get(buf, CMDS)[:8]
            elapsed_us = (time.perf_counter_ns() - start) / 1000
            all_latencies.append(elapsed_us)

    avg = sum(all_latencies) / len(all_latencies)
    mx = max(all_latencies)

    print(f"Keystrokes tested: {len(all_latencies)}")
    print(f"Avg latency:       {avg:.2f} us")
    print(f"Max latency:       {mx:.2f} us")
    print(f"Target <1ms:       {'PASS' if mx < 1000 else 'FAIL'} ({mx/1000:.4f} ms)")

    assert mx < 1000, f"Max latency {mx}us exceeds 1ms"
    print("\nAll latency tests PASSED!")

if __name__ == '__main__':
    test_latency()
