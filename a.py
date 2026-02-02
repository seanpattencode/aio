#!/usr/bin/env python3
"""a - AI agent session manager. Start daemon: python3 a.py --repl &"""
import sys, os

# If daemon running, use it (2ms). Otherwise fall through (30ms)
_SOCK = '/tmp/a.sock'
if '--repl' not in sys.argv and os.path.exists(_SOCK):
    try:
        import socket; s=socket.socket(socket.AF_UNIX); s.settimeout(0.1); s.connect(_SOCK)
        s.send('\0'.join(sys.argv[1:]).encode()); print(s.recv(65536).decode(), end=''); sys.exit(0)
    except: pass

# Generate monolith
if len(sys.argv) > 1 and sys.argv[1] in ('mono', 'monolith'):
    from glob import glob as G
    p = os.path.expanduser("~/.local/share/a/a_mono.py")
    open(p, 'w').write('\n\n'.join(f"# === {f} ===\n" + open(f).read() for f in sorted(G(os.path.dirname(__file__) + '/a_cmd/*.py'))))
    print(p); sys.exit(0)


# Command dispatch
CMDS = {
    None: 'help', '': 'help', 'help': 'help_full', 'hel': 'help_full', '--help': 'help_full', '-h': 'help_full',
    'update': 'update', 'upd': 'update', 'jobs': 'jobs', 'job': 'jobs', 'kill': 'kill', 'kil': 'kill', 'killall': 'kill',
    'attach': 'attach', 'att': 'attach', 'cleanup': 'cleanup', 'cle': 'cleanup', 'config': 'config', 'con': 'config',
    'ls': 'ls', 'diff': 'diff', 'dif': 'diff', 'send': 'send', 'sen': 'send', 'watch': 'watch', 'wat': 'watch',
    'push': 'push', 'pus': 'push', 'pull': 'pull', 'pul': 'pull', 'revert': 'revert', 'rev': 'revert',
    'set': 'set', 'settings': 'set', 'install': 'install', 'ins': 'install', 'uninstall': 'uninstall', 'uni': 'uninstall',
    'deps': 'deps', 'dep': 'deps', 'prompt': 'prompt', 'pro': 'prompt', 'gdrive': 'gdrive', 'gdr': 'gdrive',
    'add': 'add', 'remove': 'remove', 'rem': 'remove', 'rm': 'remove', 'move': 'move', 'mov': 'move', 'dash': 'dash', 'das': 'dash',
    'all': 'multi', 'a': 'multi', 'ai': 'multi', 'aio': 'multi', 'backup': 'backup', 'bak': 'backup', 'scan': 'scan', 'sca': 'scan',
    'e': 'e', 'x': 'x', 'p': 'push', 'copy': 'copy', 'cop': 'copy', 'log': 'log', 'logs': 'log', 'done': 'done',
    'agent': 'agent', 'tree': 'tree', 'tre': 'tree', 'dir': 'dir', 'web': 'web', 'ssh': 'ssh', 'run': 'run', 'hub': 'hub', 'ask': 'ask',
    'task': 'task', 'tas': 'task', 't': 'task', 'daemon': 'daemon', 'ui': 'ui', 'review': 'review',
    'n': 'note', 'note': 'note', 'i': 'i', 'rebuild': 'rebuild', 'repo': 'repo', 'sync': 'sync', 'syn': 'sync', 'login': 'login', 'docs': 'docs', 'doc': 'docs',
    'hi': 'hi', 'info': 'info',
}

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    # Experimental: a x.test1 runs a_cmd/experimental/test1.py, a x lists all
    if arg == 'x':
        d = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'a_cmd/experimental')
        cmds = sorted(f[:-3] for f in os.listdir(d) if f.endswith('.py') and f != '__init__.py')
        print("a x.<name>  run from a_cmd/experimental/\n")
        for c in cmds: m = __import__(f'a_cmd.experimental.{c}', fromlist=[c]); print(f"  {c:<10} {(m.__doc__ or '').split(chr(10))[0]}")
        return
    if arg and arg.startswith('x.'):
        try: __import__(f'a_cmd.experimental.{arg[2:]}', fromlist=[arg[2:]]).run()
        except ModuleNotFoundError: print(f"x No experimental cmd: {arg[2:]}"); sys.exit(1)
        return
    if c := CMDS.get(arg): __import__(f'a_cmd.{c}', fromlist=[c]).run()
    elif arg and arg.endswith('++') and not arg.startswith('w'): from a_cmd import wt_plus; wt_plus.run()
    elif arg and arg.startswith('w') and arg not in ('watch', 'web') and not os.path.isfile(arg): from a_cmd import wt; wt.run()
    elif arg and (os.path.isdir(os.path.expanduser(arg)) or os.path.isfile(arg) or (arg.startswith('/projects/') and os.path.isdir(os.path.expanduser('~' + arg)))): from a_cmd import dir_file; dir_file.run()
    elif arg and arg.isdigit(): from a_cmd import project_num; project_num.run()
    else: from a_cmd import sess; sess.run()

if __name__ == '__main__':
    if sys.argv[1:] == ['--repl']:
        import socket, io, contextlib
        os.path.exists(_SOCK) and os.unlink(_SOCK); s=socket.socket(socket.AF_UNIX); s.bind(_SOCK); s.listen(1)
        while (c:=s.accept()[0]):
            sys.argv=['a']+[x for x in c.recv(4096).decode().split('\0') if x]; buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                try: main()
                except SystemExit: pass
            c.send(buf.getvalue().encode()); c.close()
    else: main()
