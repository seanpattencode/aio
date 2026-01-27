"""aio i - Interactive command picker with live suggestions"""
import sys, os, tty, termios

CMDS = ['help','update','jobs','kill','attach','cleanup','config','ls','diff','send','watch',
        'push','pull','revert','set','settings','install','uninstall','deps','prompt','gdrive',
        'add','remove','move','dash','all','backup','scan','copy','log','done','agent','tree',
        'dir','web','ssh','run','hub','daemon','ui','review','note']
CACHE = os.path.expanduser("~/.local/share/aios/i_cache.txt")

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try: tty.setraw(fd); return sys.stdin.read(1)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)

def refresh_cache():
    from . _common import load_proj, load_apps, init_db
    init_db(); p, a = load_proj(), load_apps()
    items = [f"{i}:{os.path.basename(x)}" for i,x in enumerate(p)] + [f"{len(p)+i}:{n}" for i,(n,_) in enumerate(a)] + CMDS
    os.makedirs(os.path.dirname(CACHE), exist_ok=True); open(CACHE, 'w').write('\n'.join(items))

def run():
    try: items = open(CACHE).read().strip().split('\n')
    except: refresh_cache(); items = open(CACHE).read().strip().split('\n')

    if not sys.stdin.isatty():
        print('\n'.join(items)); sys.exit(0)

    # Rebuild cache in background
    if os.fork() == 0: refresh_cache(); os._exit(0)

    sys.stdout.write("\033[?25l\033[u"); buf, sel = "", 0  # Hide cursor, restore position

    while True:
        matches = [x for x in items if buf.replace(' ','').lower() in x.lower()][:8] if buf else items[:8]
        sel = min(sel, len(matches)-1) if matches else 0

        # Render
        sys.stdout.write(f"\r\033[K> {buf}\n")
        for i, m in enumerate(matches): sys.stdout.write(f"\033[K{' >' if i==sel else '  '} {m}\n")
        sys.stdout.write(f"\033[{len(matches)+1}A\033[{len(buf)+3}C\033[?25h")
        sys.stdout.flush()

        ch = getch()
        if ch == '\x1b':  # Esc or arrow
            n = sys.stdin.read(2) if sys.stdin in __import__('select').select([sys.stdin],[],[],0)[0] else ''
            if n == '[A': sel = max(0, sel-1)  # Up
            elif n == '[B': sel = min(len(matches)-1, sel+1)  # Down
            elif n == '[C': sel = min(len(matches)-1, sel+1)  # Right
            elif n == '[D': sel = max(0, sel-1)  # Left
            elif not n: break  # Plain Esc
        elif ch == '\t': sel = (sel + 1) % len(matches) if matches else 0
        elif ch == '\x7f' and buf: buf, sel = buf[:-1], 0
        elif ch == '\r' and matches:
            cmd = matches[sel].split(':')[0] if ':' in matches[sel] else matches[sel]
            print(f"\n\n\033[KRunning: aio {cmd}\n")
            os.execvp(sys.executable, [sys.executable, os.path.dirname(__file__) + '/../aio.py', cmd])
        elif ch in ('\x03', '\x04') or (ch == 'q' and not buf): break  # Ctrl+C, Ctrl+D, q
        elif ch.isalnum() or ch in '-_ ': buf, sel = buf + ch, 0

        sys.stdout.write("\033[J")

    print("\033[2B\033[K")
