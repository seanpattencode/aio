#!/usr/bin/env python3
"""Interactive search picker - pico bigram index (3 LOC)"""
import sys, os, tty, termios

ITEMS = [
    "help: Show commands", "update: Update caches", "jobs: Show running jobs",
    "kill: Stop a job", "attach: Attach to session", "config: Edit config",
    "push: Push changes", "pull: Pull changes", "sync: Sync all devices",
    "backup: Backup data", "chromium: Open browser", "chrome-debug: Debug mode",
    "github: Open GitHub", "gitlab: Open GitLab",
] + [f"project{i}: Project {i}" for i in range(50)]

# Pico index (3 lines) - dedupe per item
IX = {}
for i, u in enumerate(ITEMS):
    for p in set(u[j:j+2].lower() for j in range(len(u)-1)): IX.setdefault(p, []).append(i)

def search(q):
    q = q.lower()
    return [ITEMS[i] for i in IX.get(q[:2], range(len(ITEMS))) if q in ITEMS[i].lower()][:10]

def getch():
    fd, old = sys.stdin.fileno(), termios.tcgetattr(sys.stdin.fileno())
    try: tty.setraw(fd); return sys.stdin.read(1)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)

def run():
    buf, sel = "", 0
    print("\033[2J\033[H=== Pico Search ===\nType to filter | Enter=select | q=quit\n")

    while True:
        matches = search(buf) if buf else ITEMS[:10]
        sel = min(sel, max(0, len(matches) - 1))

        sys.stdout.write(f"\033[4;0H\033[J> {buf}_\n\n")
        for i, m in enumerate(matches):
            sys.stdout.write(f" {'>' if i == sel else ' '} {m}\n")
        sys.stdout.flush()

        ch = getch()
        if ch == '\x1b':
            import select
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                seq = sys.stdin.read(2)
                if seq in ('[A', '[D'): sel = max(0, sel - 1)  # Up/Left
                elif seq in ('[B', '[C'): sel = min(len(matches) - 1, sel + 1)  # Down/Right
            else: break
        elif ch == '\t': sel = (sel + 1) % max(1, len(matches))
        elif ch == '\x7f': buf, sel = buf[:-1], 0
        elif ch == '\r' and matches: print(f"\n\nSelected: {matches[sel]}\n"); return matches[sel]
        elif ch in ('q', '\x03', '\x04') and not buf: break
        elif ch.isprintable(): buf, sel = buf + ch, 0

    print("\033[2J\033[H")

if __name__ == '__main__': run()
