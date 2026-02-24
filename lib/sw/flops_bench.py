#!/usr/bin/env python3
"""CPU FLOPS benchmark - measures floating point performance with device comparison."""

import time
import multiprocessing
import sys

def single_core_bench(duration=5):
    """Run single-core floating point benchmark."""
    ops = 0
    start = time.time()
    x = 1.0000001
    while time.time() - start < duration:
        for _ in range(10000):
            x = x * 1.0000001
            x = x + 0.0000001
            x = x - 0.00000005
            x = x / 1.0000001
        ops += 40000
        if x > 1e100 or x < 1e-100:
            x = 1.0000001
    elapsed = time.time() - start
    return ops / elapsed

def worker(q, duration):
    """Worker process for multi-core benchmark."""
    result = single_core_bench(duration)
    q.put(result)

def multi_core_bench(cores, duration=5):
    """Run multi-core floating point benchmark."""
    q = multiprocessing.Queue()
    procs = []
    for _ in range(cores):
        p = multiprocessing.Process(target=worker, args=(q, duration))
        p.start()
        procs.append(p)
    for p in procs:
        p.join()
    total = 0
    while not q.empty():
        total += q.get()
    return total

def run_benchmark(duration=5):
    """Run full benchmark suite."""
    cores = multiprocessing.cpu_count()

    print(f"Test: CPU FLOPS")
    print(f"Duration: {duration}s | Cores: {cores}")
    print("=" * 60)

    # Single-core test
    print("\n[SINGLE-CORE] Using 1 thread")
    print("-" * 60)
    single = single_core_bench(duration)
    single_mflops = single / 1e6
    print(f"Result: {single_mflops:>8.1f} MFLOPS ({single/1e9:.4f} GFLOPS)")

    # Multi-core test
    print(f"\n[MULTI-CORE] Using {cores} threads")
    print("-" * 60)
    multi = multi_core_bench(cores, duration)
    multi_mflops = multi / 1e6
    print(f"Result: {multi_mflops:>8.1f} MFLOPS ({multi/1e9:.4f} GFLOPS)")

    scaling = multi / single
    print(f"Scaling: {scaling:.1f}x ({scaling/cores*100:.0f}% efficiency)")

    # Comparison table
    print("\n" + "=" * 60)
    print("COMPARISON (Python benchmark, similar methodology)")
    print("=" * 60)
    print(f"{'Device':<25} {'Single':>10} {'Multi':>10} {'Notes':<15}")
    print("-" * 60)
    print(f"{'>>> THIS DEVICE <<<':<25} {single_mflops:>8.1f} M {multi_mflops:>8.1f} M {'* RESULT *':<15}")
    print("-" * 60)
    print(f"{'Raspberry Pi 4':<25} {'~6':>10} {'~22':>10} {'Cortex-A72':<15}")
    print(f"{'Raspberry Pi 5':<25} {'~10':>10} {'~38':>10} {'Cortex-A76':<15}")
    print(f"{'Samsung Galaxy A54':<25} {'~7':>10} {'~40':>10} {'Exynos 1380':<15}")
    print(f"{'iPhone 12':<25} {'~15':>10} {'~80':>10} {'A14 Bionic':<15}")
    print(f"{'Samsung S21':<25} {'~12':>10} {'~70':>10} {'SD 888':<15}")
    print(f"{'Pixel 7':<25} {'~11':>10} {'~65':>10} {'Tensor G2':<15}")
    print(f"{'MacBook Air M1':<25} {'~25':>10} {'~180':>10} {'Apple M1':<15}")
    print(f"{'MacBook Pro M3':<25} {'~30':>10} {'~220':>10} {'Apple M3':<15}")
    print(f"{'Intel i5-12400':<25} {'~20':>10} {'~110':>10} {'Desktop':<15}")
    print(f"{'AMD Ryzen 7 5800X':<25} {'~22':>10} {'~160':>10} {'Desktop':<15}")
    print("-" * 60)

    print("\nTHEORETICAL PEAK (native C/C++, not Python)")
    print("-" * 60)
    print(f"{'Device':<30} {'Peak GFLOPS':>15}")
    print("-" * 60)
    print(f"{'Cortex-A55 (8 core)':<30} {'25-35':>15}")
    print(f"{'Cortex-A76 (4 core)':<30} {'40-50':>15}")
    print(f"{'Apple M1 CPU':<30} {'~90':>15}")
    print(f"{'Apple M1 GPU':<30} {'~2,600':>15}")
    print(f"{'Snapdragon 888 GPU':<30} {'~1,500':>15}")
    print(f"{'RTX 4090 GPU':<30} {'~83,000':>15}")
    print("-" * 60)
    print("\nNote: Python measures interpreter + CPU overhead.")
    print("Native code shows ~1000-5000x higher numbers.")

if __name__ == '__main__':
    duration = 5
    if len(sys.argv) > 1:
        try:
            duration = max(1, min(60, int(sys.argv[1])))
        except ValueError:
            pass
    run_benchmark(duration)
