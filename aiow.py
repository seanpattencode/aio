#!/usr/bin/env python3
"""aio warm daemon - pre-warms Python for 4-6x faster commands"""
import os, sys, socket, io

SOCK, AIO = '/tmp/aio.sock', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aio.py')

def daemon():
    os.environ['_AIO_WARM'] = '1'
    code = compile(open(AIO).read(), AIO, 'exec')
    sys.argv, sys.stdout = ['aio', 'help'], io.StringIO()
    exec(code, {'__name__': '__main__', '__file__': AIO})
    sys.stdout = sys.__stdout__
    try: os.unlink(SOCK)
    except: pass
    sock = socket.socket(socket.AF_UNIX); sock.bind(SOCK); sock.listen(5)
    print("aio warm daemon ready")
    while True:
        conn, _ = sock.accept(); data = conn.recv(8192).decode()
        if data == 'STOP': conn.close(); break
        if os.fork() == 0:
            cwd, args = data.split('\n', 1) if '\n' in data else (os.getcwd(), data)
            os.chdir(cwd); buf = io.StringIO(); sys.stdout = sys.stderr = buf
            sys.argv = ['aio'] + (args.split() if args else [])
            try: exec(code, {'__name__': '__main__', '__file__': AIO})
            except SystemExit: pass
            except Exception as e: buf.write(f"Error: {e}")
            conn.send(buf.getvalue().encode()); conn.close(); os._exit(0)
        else:
            conn.close()  # Parent closes its copy
            try: os.waitpid(-1, os.WNOHANG)  # Reap zombies non-blocking
            except: pass
    os.unlink(SOCK)

def client(args):
    s = socket.socket(socket.AF_UNIX); s.connect(SOCK)
    s.send(f"{os.getcwd()}\n{' '.join(args)}".encode()); s.shutdown(socket.SHUT_WR)
    while (d := s.recv(4096)): sys.stdout.write(d.decode()); sys.stdout.flush()

def install():
    me = os.path.abspath(__file__)
    py = sys.executable
    # Create shell client for max speed
    sh = os.path.join(os.path.dirname(me), 'aiow')
    open(sh, 'w').write(f'#!/bin/sh\nprintf "%s\\n%s" "$PWD" "$*" | nc -U /tmp/aio.sock\n')
    os.chmod(sh, 0o755)
    if sys.platform == 'darwin':  # macOS launchd
        p = os.path.expanduser('~/Library/LaunchAgents/com.aio.warm.plist')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'w').write(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.aio.warm</string>
<key>ProgramArguments</key><array><string>{py}</string><string>{me}</string><string>daemon</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>''')
        os.system(f'launchctl load {p}'); print(f"✓ Installed: {p}")
    elif os.path.exists('/data/data/com.termux'):  # Termux cron
        os.system('pkg install -y cronie 2>/dev/null; pgrep crond || crond')
        os.system(f'(crontab -l 2>/dev/null | grep -v aio.warm; echo "@reboot {py} {me} daemon") | crontab -')
        os.system(f'{py} {me} daemon &'); print("✓ Installed: crontab @reboot")
    else:  # Linux systemd
        d = os.path.expanduser('~/.config/systemd/user'); os.makedirs(d, exist_ok=True)
        open(f'{d}/aio-warm.service', 'w').write(f'[Unit]\nDescription=aio warm daemon\n[Service]\nExecStart={py} {me} daemon\nRestart=always\n[Install]\nWantedBy=default.target')
        os.system('systemctl --user daemon-reload && systemctl --user enable --now aio-warm'); print(f"✓ Installed: {d}/aio-warm.service")
    # Add alias to shell client (faster than Python client)
    rc = os.path.expanduser('~/.zshrc' if os.path.exists(os.path.expanduser('~/.zshrc')) else '~/.bashrc')
    alias = f"\nalias aiow='{sh}'\n"
    if 'aiow=' not in open(rc).read(): open(rc, 'a').write(alias); print(f"✓ Added alias: aiow -> {sh}")

def uninstall():
    if sys.platform == 'darwin':
        p = os.path.expanduser('~/Library/LaunchAgents/com.aio.warm.plist')
        os.system(f'launchctl unload {p} 2>/dev/null'); os.path.exists(p) and os.remove(p)
    elif os.path.exists('/data/data/com.termux'):
        os.system("crontab -l 2>/dev/null | grep -v aio.warm | crontab -")
    else:
        os.system('systemctl --user disable --now aio-warm 2>/dev/null')
        p = os.path.expanduser('~/.config/systemd/user/aio-warm.service')
        os.path.exists(p) and os.remove(p)
    os.system('pkill -f "aiow.py daemon"'); print("✓ Uninstalled")

def status():
    try: s = socket.socket(socket.AF_UNIX); s.connect(SOCK); s.close(); print("✓ Running")
    except: print("✗ Not running")

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'daemon': daemon()
    elif cmd == 'install': install()
    elif cmd == 'uninstall': uninstall()
    elif cmd == 'status': status()
    elif cmd == 'stop': socket.socket(socket.AF_UNIX).connect(SOCK) or None; print("Stopped")
    else:
        try: client(sys.argv[1:])
        except: print("Daemon not running. Start: python3 aiow.py daemon &\nOr install: python3 aiow.py install")
