#!/usr/bin/env python3
"""a - AI agent session manager"""
import sys, os

# Fast-path: 'a i' - pipe mode only
if len(sys.argv) > 1 and sys.argv[1] == 'i' and not sys.stdin.isatty():
    c = os.path.expanduser("~/.local/share/a/i_cache.txt")
    print('\n'.join(x for x in open(c).read().split('\n') if x and x[0] not in '<=>') if os.path.exists(c) else ''); sys.exit(0)

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
    'e': 'e', 'x': 'x', 'p': 'p', 'copy': 'copy', 'cop': 'copy', 'log': 'log', 'done': 'done',
    'agent': 'agent', 'tree': 'tree', 'tre': 'tree', 'dir': 'dir', 'web': 'web', 'ssh': 'ssh', 'run': 'run', 'hub': 'hub',
    'task': 'task', 'tas': 'task', 't': 'task', 'daemon': 'daemon', 'ui': 'ui', 'review': 'review',
    'n': 'note', 'note': 'note', 'i': 'i', 'rebuild': 'rebuild', 'repo': 'repo', 'sync': 'sync', 'syn': 'sync',
}

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if c := CMDS.get(arg): __import__(f'a_cmd.{c}', fromlist=[c]).run()
    elif arg and arg.endswith('++') and not arg.startswith('w'): from a_cmd import wt_plus; wt_plus.run()
    elif arg and arg.startswith('w') and arg not in ('watch', 'web') and not os.path.isfile(arg): from a_cmd import wt; wt.run()
    elif arg and (os.path.isdir(os.path.expanduser(arg)) or os.path.isfile(arg) or (arg.startswith('/projects/') and os.path.isdir(os.path.expanduser('~' + arg)))): from a_cmd import dir_file; dir_file.run()
    elif arg and arg.isdigit(): from a_cmd import project_num; project_num.run()
    else: from a_cmd import sess; sess.run()

if __name__ == '__main__':
    main()
