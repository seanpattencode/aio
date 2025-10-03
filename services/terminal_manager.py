#!/usr/bin/env python3
import sys, os, pty, termios, struct, fcntl, signal
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db

_pty_sessions = {}

def create_session(worktree_id, worktree_path):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
    pid = os.fork()
    if pid == 0:
        [os.dup2(slave, fd) for fd in [0, 1, 2]]
        [os.close(fd) for fd in [master, slave]]
        os.setsid()
        os.chdir(worktree_path)
        os.execv('/bin/bash', ['bash'])
    os.close(slave)
    os.set_blocking(master, False)
    _pty_sessions[worktree_id] = {"master": master, "pid": pid, "path": worktree_path}
    sessions = aios_db.read("terminal_sessions") or {}
    sessions[worktree_id] = {"pid": pid, "path": worktree_path, "created": __import__('time').time()}
    aios_db.write("terminal_sessions", sessions)
    return master

get_session = lambda wt_id: _pty_sessions.get(wt_id)
send_data = lambda wt_id, data: os.write(_pty_sessions[wt_id]["master"], data) if wt_id in _pty_sessions else None
read_data = lambda wt_id, size=65536: (lambda s: os.read(s["master"], size) if s else b'')(_pty_sessions.get(wt_id))
kill_session = lambda wt_id: (os.kill(_pty_sessions[wt_id]["pid"], signal.SIGTERM), os.close(_pty_sessions[wt_id]["master"]), _pty_sessions.pop(wt_id)) if wt_id in _pty_sessions else None

if __name__ == "__main__":
    cmd, wt_id, wt_path = (sys.argv + ["list", "default", str(Path.cwd())])[:3]
    {"create": lambda: (create_session(wt_id, wt_path), print(f"Created: {wt_id}")),
     "list": lambda: [print(f"{k}: pid={v['pid']} -> {v['path']}") for k, v in (aios_db.read("terminal_sessions") or {}).items()]}.get(cmd, lambda: None)()
