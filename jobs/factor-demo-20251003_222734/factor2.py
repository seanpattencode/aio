#!/usr/bin/env python3
import sys

from sympy import factorint


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: factor2.py <integer>")

    original = int(sys.argv[1])
    factors: list[int] = []

    for prime, exponent in factorint(original).items():
        factors.extend([prime] * exponent)

    print(factors or [original])


if __name__ == "__main__":
    main()
