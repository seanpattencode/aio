"""aio i - Interactive command picker with live suggestions"""
import sys, os, tty, termios

from ._common import DATA_DIR, HELP_SHORT
CACHE, HELP_CACHE = f"{DATA_DIR}/i_cache.txt", f"{DATA_DIR}/help_cache.txt"

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try: tty.setraw(fd); return sys.stdin.read(1)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)

def refresh_cache():
    from .update import refresh_caches; refresh_caches()

def run():
    try: items = [x for x in open(CACHE).read().strip().split('\n') if x and not x.startswith(('<','=','>','#'))]
    except: refresh_cache(); items = open(CACHE).read().strip().split('\n')
    if not items: refresh_cache(); items = open(CACHE).read().strip().split('\n')

    if len(sys.argv)>2 and (m:=next((x for x in items if ' '.join(sys.argv[2:]).lower() in x.lower()),None)): c=m.split(':')[0].strip()if':'in m else m; print(f"a {c}"); __import__('subprocess').run([sys.executable,__file__.replace('i.py','../a.py')]+c.split()); sys.exit(0)
    elif len(sys.argv)>2: print(f"x No match"); sys.exit(1)
    if not sys.stdin.isatty(): print('\n'.join(items)); sys.exit(0)

    if os.fork() == 0: refresh_cache(); os._exit(0)  # Rebuild cache in background

    ix = {}
    for i, u in enumerate(items):
        for p in set(u[j:j+2].lower() for j in range(len(u)-1)): ix.setdefault(p, []).append(i)
    def search(q): q=q.lower(); return sorted([items[i] for i in ix.get(q[:2],range(len(items))) if q in items[i].lower()], key=lambda x:(q not in x.lower()[:len(q)],x.lower().find(q)))[:10]

    print((open(HELP_CACHE).read().strip() if os.path.exists(HELP_CACHE) else "") + "\n" + "-"*40 + "\nFilter (Tab=cycle, Enter=run, Esc=quit)\n"); buf, sel = "", 0

    while True:
        matches = search(buf) if buf else items[:10]
        sel = min(sel, len(matches)-1) if matches else 0

        # Render search at bottom
        sys.stdout.write(f"\r\033[K> {buf}\n")
        for i, m in enumerate(matches): sys.stdout.write(f"\033[K{' >' if i==sel else '  '} {m}\n")
        sys.stdout.write(f"\033[{len(matches)+1}A\033[{len(buf)+3}C\033[?25h")
        sys.stdout.flush()

        ch = getch()
        if ch == '\x1b': break  # Esc
        elif ch == '\t': sel = (sel + 1) % len(matches) if matches else 0
        elif ch == '\x7f' and buf: buf, sel = buf[:-1], 0
        elif ch == '\r':
            cmd = buf if ' ' in buf else (matches[sel].split(':')[0].strip() if matches and ':' in matches[sel] else (matches[sel].strip() if matches else buf))
            if not cmd: continue
            via_a = ' ' in buf or matches; print(f"\n\n\033[KRunning: {'a '+cmd if via_a else cmd}\n")
            __import__('subprocess').run([sys.executable,__file__.replace('i.py','../a.py')]+cmd.split() if via_a else cmd.split()); break
        elif ch in ('\x03', '\x04') or (ch == 'q' and not buf): break  # Ctrl+C, Ctrl+D, q
        elif ch.isalnum() or ch in '-_ ': buf, sel = buf + ch, 0

        sys.stdout.write("\033[J")

    print("\033[2B\033[K")
