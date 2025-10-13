"""Quicksort algorithm implementation.

This module exposes both a functional quicksort that returns a new list
and an in-place variant for cases where mutating the input is acceptable.
"""
from __future__ import annotations

from typing import MutableSequence, Sequence, TypeVar, List


T = TypeVar("T")


def quicksort(values: Sequence[T]) -> List[T]:
    """Return a new list containing the items from ``values`` in sorted order."""
    if len(values) <= 1:
        return list(values)

    pivot_index = len(values) // 2
    pivot = values[pivot_index]

    left: List[T] = [item for item in values if item < pivot]
    middle: List[T] = [item for item in values if item == pivot]
    right: List[T] = [item for item in values if item > pivot]

    return quicksort(left) + middle + quicksort(right)


def quicksort_inplace(values: MutableSequence[T]) -> None:
    """Sort ``values`` in place using the quicksort algorithm."""

    def _sort(low: int, high: int) -> None:
        if low >= high:
            return

        pivot_index = partition(low, high)
        _sort(low, pivot_index - 1)
        _sort(pivot_index + 1, high)

    def partition(low: int, high: int) -> int:
        pivot = values[high]
        i = low - 1
        for j in range(low, high):
            if values[j] <= pivot:
                i += 1
                values[i], values[j] = values[j], values[i]
        values[i + 1], values[high] = values[high], values[i + 1]
        return i + 1

    _sort(0, len(values) - 1)


__all__ = ["quicksort", "quicksort_inplace"]
