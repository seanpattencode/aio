import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sort import quicksort


def test_quicksort_benchmark_1000_random_numbers():
    """Benchmark quicksort on a reproducible set of 1000 random ints."""
    random.seed(2024)
    data = [random.randint(-1_000_000, 1_000_000) for _ in range(1000)]

    start = time.perf_counter()
    result = quicksort(data)
    duration = time.perf_counter() - start

    assert result == sorted(data)
    assert duration < 0.5, f"quicksort took {duration:.6f}s for 1000 items"
