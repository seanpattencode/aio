#!/usr/bin/env python3
"""Split - all modules imported eagerly"""
import sys, os, subprocess, socket, time, shutil, atexit
sys.path.insert(0, os.path.dirname(__file__))
import cmd_a, cmd_b, cmd_c  # eager import

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'a'
    print({'a': cmd_a.run, 'b': cmd_b.run, 'c': cmd_c.run}.get(cmd, cmd_a.run)())
