#!/usr/bin/env python3
import sys
from sympy import factorint
from itertools import chain, repeat


def _read_input() -> int:
    if len(sys.argv) > 1:
        return int(sys.argv[1])
    return int(sys.stdin.readline())


def main() -> None:
    n = _read_input()
    factors = factorint(n)
    ordered_factors = chain.from_iterable(
        repeat(prime, exponent) for prime, exponent in sorted(factors.items())
    )
    print(*ordered_factors)


if __name__ == "__main__":
    main()
