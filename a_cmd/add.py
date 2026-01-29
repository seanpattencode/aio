"""aio add - Add project or command"""
import sys, os
from . _common import init_db, add_proj, add_app, auto_backup, list_all

def run():
    init_db()
    args = [a for a in sys.argv[2:] if a != '--global']
    ig = '--global' in sys.argv[2:]
    if len(args) >= 2 and not os.path.isdir(os.path.expanduser(args[0])):
        interp = ['python', 'python3', 'node', 'npm', 'ruby', 'perl', 'java', 'go', 'sh', 'bash', 'npx']
        if args[0] in interp:
            cv = ' '.join(args); print(f"Command: {cv}")
            cn = input("Name for this command: ").strip()
            if not cn: print("x Cancelled"); sys.exit(1)
        else: cn, cv = args[0], ' '.join(args[1:])
        cwd, home = os.getcwd(), os.path.expanduser('~')
        if not ig and cwd != home and not cv.startswith('cd '): cv = f"cd {cwd.replace(home, '~')} && {cv}"
        ok, msg = add_app(cn, cv); print(f"{'✓' if ok else 'x'} {msg}")
        if ok: auto_backup(); list_all()
        sys.exit(0 if ok else 1)
    path = os.path.abspath(os.path.expanduser(args[0])) if args else os.getcwd()
    ok, msg = add_proj(path); print(f"{'✓' if ok else 'x'} {msg}")
    if ok: auto_backup(); list_all()
    sys.exit(0 if ok else 1)
