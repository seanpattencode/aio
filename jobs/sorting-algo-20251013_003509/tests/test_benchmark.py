import pathlib
import random
import sys
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sort import quicksort, quicksort_inplace


def test_quicksort_benchmark_1000_random_numbers() -> None:
    rng = random.Random(0)
    values = [rng.random() for _ in range(1000)]
    expected = sorted(values)

    start = time.perf_counter()
    sorted_values = quicksort(values)
    quicksort_duration = time.perf_counter() - start

    assert sorted_values == expected
    assert quicksort_duration < 1.0, f"quicksort took {quicksort_duration:.4f}s"

    values_inplace = list(values)
    start = time.perf_counter()
    quicksort_inplace(values_inplace)
    inplace_duration = time.perf_counter() - start

    assert values_inplace == expected
    assert inplace_duration < 1.0, f"quicksort_inplace took {inplace_duration:.4f}s"
