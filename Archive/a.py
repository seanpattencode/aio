#!/usr/bin/env python3
"""a - Interactive command picker for all Linux commands. Self-installing."""
import sys, os, tty, termios

CACHE = os.path.expanduser("~/.cache/a/commands.txt")
BIN = os.path.expanduser("~/.local/bin/a")

def get_commands():
    """Get all executable commands from PATH"""
    cmds = set()
    for p in os.environ.get('PATH', '').split(':'):
        try: cmds.update(f for f in os.listdir(p) if os.access(f"{p}/{f}", os.X_OK))
        except: pass
    return sorted(cmds)

def refresh_cache():
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    open(CACHE, 'w').write('\n'.join(get_commands()))

def getch():
    fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
    try: tty.setraw(fd); return sys.stdin.read(1)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)

def install():
    """Install 'a' command and bash function"""
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    if os.path.abspath(__file__) != BIN:
        open(BIN, 'w').write(open(__file__).read()); os.chmod(BIN, 0o755)
    rc = os.path.expanduser("~/.bashrc")
    if os.path.exists(rc) and 'a() {' not in open(rc).read():
        open(rc, 'a').write('''
a() {
    local c=~/.cache/a/commands.txt
    [[ -t 0 ]] && { printf "Type to filter, Tab=cycle, Enter=run, Esc=quit\\n\\n> \\033[s\\n"; head -8 "$c" 2>/dev/null | awk 'NR==1{print " > "$0}NR>1{print "   "$0}'; printf '\\033[?25l'; command python3 ~/.local/bin/a "$@"; printf '\\033[?25h'; return; }
    command python3 ~/.local/bin/a "$@"
}
''')
    refresh_cache()
    print(f"Installed to {BIN}\nRun: source ~/.bashrc && a")

def run():
    try: items = open(CACHE).read().strip().split('\n')
    except: items = get_commands(); refresh_cache()

    if not sys.stdin.isatty(): print('\n'.join(items)); return
    if os.fork() == 0: refresh_cache(); os._exit(0)

    sys.stdout.write("\033[?25l\033[u"); buf, sel = "", 0

    while True:
        matches = [x for x in items if buf.lower() in x.lower()][:8] if buf else items[:8]
        sel = min(sel, len(matches)-1) if matches else 0

        sys.stdout.write(f"\r\033[K> {buf}\n")
        for i, m in enumerate(matches): sys.stdout.write(f"\033[K{' >' if i==sel else '  '} {m}\n")
        sys.stdout.write(f"\033[{len(matches)+1}A\033[{len(buf)+3}C\033[?25h")
        sys.stdout.flush()

        ch = getch()
        if ch == '\x1b':
            n = sys.stdin.read(2) if sys.stdin in __import__('select').select([sys.stdin],[],[],0)[0] else ''
            if n == '[A': sel = max(0, sel-1)
            elif n == '[B': sel = min(len(matches)-1, sel+1)
            elif not n: break
        elif ch == '\t': sel = (sel + 1) % len(matches) if matches else 0
        elif ch == '\x7f' and buf: buf, sel = buf[:-1], 0
        elif ch == '\r' and matches:
            cmd = matches[sel]
            print(f"\n\n\033[KRun: {cmd}\n")
            os.execvp(cmd, [cmd])
        elif ch in ('\x03', '\x04') or (ch == 'q' and not buf): break
        elif ch.isprintable(): buf, sel = buf + ch, 0
        sys.stdout.write("\033[J")

    print("\033[?25h\033[2B\033[K")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'install': install()
    else: run()
