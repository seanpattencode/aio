#!/usr/bin/env python3
"""aio modular - independent commands split out"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'commands'))

# Eager imports for warming
import diff, pull, push, copy, update, revert

CMDS = {
    'diff': diff.run, 'dif': diff.run,
    'pull': pull.run, 'pul': pull.run,
    'push': push.run, 'pus': push.run,
    'copy': copy.run, 'cop': copy.run,
    'update': update.run, 'upd': update.run,
    'revert': revert.run, 'rev': revert.run,
}

def cmd_help(args):
    print("aio_mod - modular commands\n  diff  pull  push  copy  update  revert")

if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    CMDS.get(arg, cmd_help)(sys.argv[2:])
