import sys, os, subprocess as S, time, platform, shutil, shlex
from os.path import exists, isdir, join, dirname, expanduser

PORT = 1111
_LIB = dirname(dirname(os.path.realpath(__file__)))
_uv = expanduser('~/.local/bin/uv')
_UV = shutil.which('uv') or (_uv if os.access(_uv, os.X_OK) else None)
_MAC = platform.system() == 'Darwin'
_TERMUX = isdir('/data/data/com.termux')
_r = lambda c: S.run(c, capture_output=True)
_kill = lambda: _r(['pkill','-9','-f','ui.ui_'])

def _url(p): return f'http://localhost:{p}'

def _cmd(m, p):
    s = f'{_LIB}/ui/{m}.py'
    if _UV: return [_UV, 'run', '--script', s, str(p)]
    vp = join(dirname(_LIB), 'adata', 'venv', 'bin', 'python')
    py = vp if os.access(vp, os.X_OK) else sys.executable
    return [py, '-c', f"from ui.{m} import run;run({p})"]

def _bg(m, p):
    S.Popen(_cmd(m, p), start_new_session=True, stdout=S.DEVNULL, env=os.environ|{'PYTHONPATH':_LIB})
    time.sleep(0.3); u = _url(p)
    if exists('/proc/sys/fs/binfmt_misc/WSLInterop'):
        S.Popen(['cmd.exe', '/c', 'start', u], stdout=S.DEVNULL, stderr=S.DEVNULL)
    else: import webbrowser; webbrowser.open(u)

def _plist(): return expanduser('~/Library/LaunchAgents/com.a.ui.plist')
def _unit(): return expanduser('~/.config/systemd/user/a-ui.service')
def _svdir(): return join(os.environ.get('PREFIX', '/usr'), 'var/service/a-ui')

def _svc_off():
    if _MAC:
        p = _plist()
        if exists(p): _r(['launchctl', 'unload', p]); os.remove(p)
    elif _TERMUX:
        sd = _svdir()
        if isdir(sd): _r(['sv', 'down', 'a-ui']); _r(['rm', '-rf', sd])
    else:
        _r(['systemctl', '--user', 'disable', '--now', 'a-ui'])
        u = _unit()
        if exists(u): os.remove(u)

def _svc_on(m='ui_full', p=PORT):
    rc = _cmd(m, p); cmd = shlex.join(rc)
    if _MAC:
        pf = _plist(); _svc_off()
        os.makedirs(dirname(pf), exist_ok=True)
        args = ''.join(f'\n        <string>{a}</string>' for a in rc)
        with open(pf, 'w') as f:
            f.write(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.a.ui</string>
    <key>ProgramArguments</key><array>{args}
    </array>
    <key>EnvironmentVariables</key><dict>
        <key>PYTHONPATH</key><string>{_LIB}</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardErrorPath</key><string>/tmp/a-ui.err</string>
</dict>
</plist>''')
        _r(['launchctl', 'load', pf]); return True
    if _TERMUX:
        sd = _svdir(); _svc_off(); os.makedirs(sd, exist_ok=True); rs = join(sd, 'run')
        prefix = os.environ.get('PREFIX', '/data/data/com.termux/files/usr')
        with open(rs, 'w') as f: f.write(f'#!{prefix}/bin/sh\nexport PYTHONPATH={_LIB}\nexec {cmd}\n')
        os.chmod(rs, 0o755); _r(['sv', 'up', 'a-ui']); return True
    if _r(['systemctl', '--user', '--version']).returncode == 0:
        _svc_off(); ud = dirname(_unit()); os.makedirs(ud, exist_ok=True)
        with open(_unit(), 'w') as f:
            f.write(f'[Unit]\nDescription=a UI server\n[Service]\nExecStart={cmd}\nEnvironment=PYTHONPATH={_LIB}\nRestart=always\nRestartSec=2\n[Install]\nWantedBy=default.target\n')
        _r(['systemctl', '--user', 'daemon-reload']); _r(['systemctl', '--user', 'enable', '--now', 'a-ui']); return True
    return False

def run():
    a = sys.argv[2:]
    if a and a[0][0] == 'k':
        _kill(); print('Killed (service will restart)')
    elif a and a[0] == 'on':
        if _svc_on(): print(f'UI service on — {_url(PORT)}')
        else: print('No service manager (use a ui)'); sys.exit(1)
    elif a and a[0] == 'off':
        _svc_off(); _kill(); print('UI service off')
    else:
        p = int(a[0]) if a and a[0].isdigit() else PORT
        _kill(); _bg('ui_full', p)
        print(f"{_url(p)}\n  on  auto-start service\n  off stop service\n  k   kill")

if __name__ == '__main__': run()
