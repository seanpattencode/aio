"""Quicksort implementation.

This module exposes a single `quicksort` function that sorts any sequence of
comparable items and returns a new list containing those items in ascending
order.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, TypeVar

T = TypeVar("T")


def quicksort(values: Sequence[T]) -> List[T]:
    """Return a sorted list containing the items from `values`.

    The implementation uses the classic recursive quicksort algorithm with the
    first element as the pivot. It keeps the original sequence untouched and
    constructs new lists for the partitions so callers do not see in-place
    modifications.
    """
    items = list(values)
    if len(items) <= 1:
        return items

    pivot = items[0]
    less: List[T] = []
    greater: List[T] = []
    pivots: List[T] = []

    for item in items:
        if item < pivot:
            less.append(item)
        elif item > pivot:
            greater.append(item)
        else:
            pivots.append(item)

    return quicksort(less) + pivots + quicksort(greater)


if __name__ == "__main__":
    sample = [5, 3, 8, 4, 2, 7, 1, 10]
    print(quicksort(sample))
