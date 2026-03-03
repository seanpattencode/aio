#!/usr/bin/env python3
"""Interactive typing dispatch demo - shows suggestions as you type"""
import sys, tty, termios, time

CMDS = ['help','update','jobs','kill','attach','cleanup','config','ls','diff','send','watch',
        'push','pull','revert','set','settings','install','uninstall','deps','prompt','gdrive',
        'add','remove','move','dash','all','backup','scan','copy','log','done','agent','tree',
        'dir','web','ssh','run','hub','daemon','ui','review','note','e','x','p','n']

# Build prefix dict (fastest method)
PREFIX = {}
for c in CMDS:
    for i in range(1, len(c)+1):
        PREFIX.setdefault(c[:i], []).append(c)

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try: tty.setraw(fd); return sys.stdin.read(1)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)

def main():
    print("Type to see suggestions (Enter=select, Esc=quit)\n")
    buf = ""
    while True:
        # Get suggestions
        start = time.perf_counter_ns()
        matches = PREFIX.get(buf, CMDS[:8] if not buf else [])[:8]
        elapsed_us = (time.perf_counter_ns() - start) / 1000

        # Display
        sys.stdout.write(f"\r\033[K> {buf}_ ({elapsed_us:.1f}us)\n\033[K  ")
        sys.stdout.write("  ".join(f"\033[7m{m}\033[0m" if m == buf else m for m in matches))
        sys.stdout.write(f"\033[2A\r\033[{len(buf)+3}C")
        sys.stdout.flush()

        ch = getch()
        if ch == '\x1b': break  # Esc
        elif ch == '\x7f' and buf: buf = buf[:-1]  # Backspace
        elif ch == '\r':  # Enter
            if matches: print(f"\n\n\033[KSelected: {matches[0]}"); break
        elif ch.isalnum() or ch in '-_': buf += ch

        sys.stdout.write("\033[1B\r")  # Move down to clear suggestion line

    print("\033[2B")  # Move past display

if __name__ == '__main__':
    main()
