#!/usr/bin/env python3
"""Disk read/write speed test - shows both cached and direct I/O results."""

import os
import time
import ctypes

def test_disk_speed(path=None, size_mb=512):
    """Test disk speeds with and without OS cache."""
    if path is None:
        path = os.path.expanduser("~/speedtest.tmp")

    size_bytes = size_mb * 1024 * 1024
    block_size = 1024 * 1024  # 1MB

    print(f"Test: {path}")
    print(f"Size: {size_mb} MB | Block: 1 MB")
    print("=" * 50)

    libc = ctypes.CDLL("libc.so.6", use_errno=True)

    # Allocate aligned memory for O_DIRECT
    buf_ptr = ctypes.c_void_p()
    libc.posix_memalign(ctypes.byref(buf_ptr), 4096, block_size)
    data = b'\x00' * block_size

    try:
        # ========== CACHED RESULTS ==========
        print("\n[CACHED] Using OS page cache (RAM)")
        print("-" * 50)

        # Cached write
        with open(path, 'wb', buffering=0) as f:
            start = time.perf_counter()
            for _ in range(size_mb):
                f.write(data)
            f.flush()
            # NO fsync - let cache do its thing
        cached_write_time = time.perf_counter() - start
        cached_write = size_mb / cached_write_time
        print(f"Write: {cached_write:>8.1f} MB/s ({cached_write_time:.3f}s)")

        # Cached read (file is hot in cache)
        with open(path, 'rb') as f:
            start = time.perf_counter()
            while f.read(block_size):
                pass
        cached_read_time = time.perf_counter() - start
        cached_read = size_mb / cached_read_time
        print(f"Read:  {cached_read:>8.1f} MB/s ({cached_read_time:.3f}s)")

        os.remove(path)

        # ========== DIRECT I/O RESULTS ==========
        print("\n[O_DIRECT] Bypassing cache (actual disk)")
        print("-" * 50)

        # Direct write
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_DIRECT
        fd = os.open(path, flags, 0o644)

        start = time.perf_counter()
        for _ in range(size_mb):
            ret = libc.write(fd, buf_ptr, block_size)
            if ret < 0:
                raise OSError(ctypes.get_errno(), "write failed")
        os.fsync(fd)
        direct_write_time = time.perf_counter() - start
        os.close(fd)
        direct_write = size_mb / direct_write_time
        print(f"Write: {direct_write:>8.1f} MB/s ({direct_write_time:.2f}s)")

        # Direct read
        flags = os.O_RDONLY | os.O_DIRECT
        fd = os.open(path, flags)

        start = time.perf_counter()
        total = 0
        while total < size_bytes:
            ret = libc.read(fd, buf_ptr, block_size)
            if ret <= 0:
                break
            total += ret
        direct_read_time = time.perf_counter() - start
        os.close(fd)
        direct_read = size_mb / direct_read_time
        print(f"Read:  {direct_read:>8.1f} MB/s ({direct_read_time:.2f}s)")

        # ========== COMPARISON ==========
        print("\n" + "=" * 50)
        print("COMPARISON (MB/s)")
        print("=" * 50)
        print(f"{'':10} {'Cached':>14} {'Direct':>14} {'Cache Boost':>12}")
        print(f"{'-'*10} {'-'*14} {'-'*14} {'-'*12}")
        print(f"{'Write':<10} {cached_write:>12.1f}   {direct_write:>12.1f}   {cached_write/direct_write:>10.1f}x")
        print(f"{'Read':<10} {cached_read:>12.1f}   {direct_read:>12.1f}   {cached_read/direct_read:>10.1f}x")
        print(f"\nCached  = data in RAM (OS page cache)")
        print(f"Direct  = actual disk hardware speed")

    except OSError as e:
        print(f"O_DIRECT failed: {e}")

    finally:
        libc.free(buf_ptr)
        if os.path.exists(path):
            os.remove(path)

if __name__ == '__main__':
    test_disk_speed()
