#!/usr/bin/env python3
import sys

try:
    from sympy import factorint
except ImportError as exc:
    raise SystemExit("sympy is required: pip install sympy") from exc


def read_input(argv):
    return int(argv[1]) if len(argv) > 1 else int(input("n: "))


def main():
    n = read_input(sys.argv)
    factors = factorint(n, multiple=True)
    print(*factors)


if __name__ == "__main__":
    main()
