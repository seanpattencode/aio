#!/usr/bin/env python3
"""Warm daemon for testing monolith vs split"""
import os, sys, socket, io

SOCK = '/tmp/test_warm.sock'

def daemon(target):
    code = compile(open(target).read(), target, 'exec')
    # Pre-warm: execute once to load all imports
    sys.argv, sys.stdout = ['test', 'a'], io.StringIO()
    exec(code, {'__name__': '__main__', '__file__': os.path.abspath(target)})
    sys.stdout = sys.__stdout__

    try: os.unlink(SOCK)
    except: pass
    sock = socket.socket(socket.AF_UNIX); sock.bind(SOCK); sock.listen(5)
    print(f"warm daemon ready: {target}")

    while True:
        conn, _ = sock.accept(); data = conn.recv(1024).decode()
        if data == 'STOP': conn.close(); break
        if os.fork() == 0:
            buf = io.StringIO(); sys.stdout = buf
            sys.argv = ['test'] + (data.split() if data else ['a'])
            try: exec(code, {'__name__': '__main__', '__file__': os.path.abspath(target)})
            except SystemExit: pass
            conn.send(buf.getvalue().encode()); conn.close(); os._exit(0)
        conn.close()
        try: os.waitpid(-1, os.WNOHANG)
        except: pass
    os.unlink(SOCK)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        daemon(sys.argv[1])
