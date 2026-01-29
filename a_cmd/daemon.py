#!/usr/bin/env python3
"""aio warm daemon - pre-warms Python for 4-6x faster commands"""
import os, sys, socket, io

SOCK, AIO = '/tmp/aio.sock', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'aio.py')

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
    # Symlink shell client to ~/.local/bin (like VS Code does)
    sh_src = os.path.join(os.path.dirname(me), 'aiow')
    sh_dst = os.path.expanduser('~/.local/bin/aiow')
    os.makedirs(os.path.dirname(sh_dst), exist_ok=True)
    os.path.exists(sh_dst) and os.remove(sh_dst)
    os.symlink(sh_src, sh_dst); print(f"✓ Symlinked: {sh_dst} -> {sh_src}")
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

def uninstall():
    sh = os.path.expanduser('~/.local/bin/aiow')
    os.path.exists(sh) and os.remove(sh)
    if sys.platform == 'darwin':
        p = os.path.expanduser('~/Library/LaunchAgents/com.aio.warm.plist')
        os.system(f'launchctl unload {p} 2>/dev/null'); os.path.exists(p) and os.remove(p)
    elif os.path.exists('/data/data/com.termux'):
        os.system("crontab -l 2>/dev/null | grep -v aio.warm | crontab -")
    else:
        os.system('systemctl --user disable --now aio-warm 2>/dev/null')
        p = os.path.expanduser('~/.config/systemd/user/aio-warm.service')
        os.path.exists(p) and os.remove(p)
    os.system('pkill -f "daemon.py daemon"'); print("✓ Uninstalled")

def status():
    try: s = socket.socket(socket.AF_UNIX); s.connect(SOCK); s.close(); print("✓ Running")
    except: print("✗ Not running")

def run():
    cmd = sys.argv[2] if len(sys.argv) > 2 else ''
    if cmd in ('start', 'daemon'): daemon()
    elif cmd == 'install': install()
    elif cmd == 'uninstall': uninstall()
    elif cmd == 'status': status()
    elif cmd == 'stop': socket.socket(socket.AF_UNIX).connect(SOCK) or None; print("Stopped")
    else: print("aio daemon [start|stop|status|install|uninstall]")

if __name__ == '__main__':
    sys.argv = ['aio', 'daemon'] + sys.argv[1:]  # Normalize for run()
    run()
