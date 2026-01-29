import sys, os, subprocess, webbrowser

def run():
    a = sys.argv[2:]
    if a and a[0] in ('full', 'f'):
        from . import ui_full; p = int(a[1]) if len(a) > 1 and a[1].isdigit() else 8080; ui_full.run(p)
    elif a and a[0] in ('xterm', 'x', 'clean', 'c'):
        from . import ui_xterm; p = int(a[1]) if len(a) > 1 and a[1].isdigit() else 8080; ui_xterm.run(p)
    elif a and a[0] == '--install':
        os.makedirs(os.path.expanduser('~/.config/autostart'), exist_ok=True)
        open(os.path.expanduser('~/.config/autostart/aioUI.desktop'), 'w').write(f'[Desktop Entry]\nType=Application\nExec=python3 {os.path.abspath(__file__)}\nName=aioUI')
    elif a and a[0].isdigit():
        from . import ui_full; ui_full.run(int(a[0]))
    else:
        print("1) full    Command box + xterm\n2) xterm   Clean terminal only")
        c = input("\n> ").strip()
        if c in ('1', 'full', 'f'): from . import ui_full; ui_full.run(8080)
        elif c in ('2', 'xterm', 'x', 'c'): from . import ui_xterm; ui_xterm.run(8080)
