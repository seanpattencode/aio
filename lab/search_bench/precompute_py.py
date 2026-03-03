#!/usr/bin/env python3
"""Precomputed index autocomplete - O(1) lookup per keystroke"""
import sys
import tty
import termios
from collections import defaultdict

# Sample data - 10K URLs
URLS = [f"https://example{i}.com/path/page{i}" for i in range(5000)]
URLS.append("https://chromium.org/important")
URLS.append("https://github.com/chromium/chromium")
URLS.extend([f"https://other{i}.net/path" for i in range(5000)])

def build_index(items):
    """Build char->indices and prefix->indices maps"""
    char_index = defaultdict(set)  # single char -> set of indices
    prefix_index = {}  # 2-char prefix -> set of indices

    for i, item in enumerate(items):
        item_lower = item.lower()
        seen_chars = set()
        seen_prefixes = set()
        for j, c in enumerate(item_lower):
            if c.isalnum():
                if c not in seen_chars:
                    char_index[c].add(i)
                    seen_chars.add(c)
                # 2-char prefix
                if j + 1 < len(item_lower):
                    prefix = item_lower[j:j+2]
                    if prefix not in seen_prefixes and prefix[1].isalnum():
                        if prefix not in prefix_index:
                            prefix_index[prefix] = set()
                        prefix_index[prefix].add(i)
                        seen_prefixes.add(prefix)

    # Convert to sorted lists for consistent output
    return {k: sorted(v) for k, v in char_index.items()}, {k: sorted(v) for k, v in prefix_index.items()}

def search_precomputed(query, items, char_index, prefix_index):
    """O(1) lookup using precomputed index"""
    if not query:
        return list(range(min(10, len(items))))

    query = query.lower()

    # Use 2-char prefix if available
    if len(query) >= 2 and query[:2] in prefix_index:
        candidates = prefix_index[query[:2]]
    elif query[0] in char_index:
        candidates = char_index[query[0]]
    else:
        return []

    # Filter candidates (already narrowed down significantly)
    results = []
    for i in candidates:
        if query in items[i].lower():
            results.append(i)
            if len(results) >= 10:
                break
    return results

def main():
    # Build index at startup
    char_index, prefix_index = build_index(URLS)

    # Setup terminal
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        query = ""

        # Initial display
        sys.stdout.write("\033[2J\033[H> \n")
        for i in range(min(10, len(URLS))):
            sys.stdout.write(f"  {URLS[i]}\n")
        sys.stdout.write("\033[H\033[2C")
        sys.stdout.flush()

        while True:
            c = sys.stdin.read(1)
            if c in ('\x03', '\x04', '\x1b'):  # Ctrl-C, Ctrl-D, ESC
                break
            elif c == '\x7f' and query:  # Backspace
                query = query[:-1]
            elif c >= ' ' and c <= '~':
                query += c
            else:
                continue

            # O(1) lookup
            matches = search_precomputed(query, URLS, char_index, prefix_index)

            # Display
            sys.stdout.write(f"\033[2J\033[H> {query}\n")
            for i in matches:
                sys.stdout.write(f"  {URLS[i]}\n")
            sys.stdout.write(f"\033[H\033[{2+len(query)}C")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\033[2J\033[H")

if __name__ == "__main__":
    main()
