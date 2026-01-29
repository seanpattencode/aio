"""aio <dir|file> - Open directory or file"""
import sys, os, subprocess as sp

def run():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if os.path.isdir(os.path.expanduser(arg)):
        d = os.path.expanduser('~' + arg) if arg.startswith('/projects/') else os.path.expanduser(arg)
        print(f"{d}", flush=True)
        sp.run(['ls', d])
    elif os.path.isfile(arg):
        ext = os.path.splitext(arg)[1].lower()
        if ext == '.py':
            sys.exit(sp.run([sys.executable, arg] + sys.argv[2:]).returncode)
        elif ext in ('.html', '.htm'):
            __import__('webbrowser').open('file://' + os.path.abspath(arg))
        elif ext == '.md':
            os.execvp(os.environ.get('EDITOR', 'nvim'), [os.environ.get('EDITOR', 'nvim'), arg])
