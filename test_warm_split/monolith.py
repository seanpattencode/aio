#!/usr/bin/env python3
"""Monolith - heavy imports like aio.py"""
import sys, os, json, sqlite3, subprocess, re, socket, time, shutil, atexit
from datetime import datetime
from pathlib import Path

def cmd_a():
    return f"cmd_a: {json.dumps({'x': 1})} {datetime.now()}"

def cmd_b():
    return f"cmd_b: {sqlite3.sqlite_version} {shutil.which('python3')}"

def cmd_c():
    return f"cmd_c: {re.match(r'\\d+', '123').group()} {Path.cwd()}"

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'a'
    print({'a': cmd_a, 'b': cmd_b, 'c': cmd_c}.get(cmd, cmd_a)())
