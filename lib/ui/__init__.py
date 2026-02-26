import sys, os, subprocess as S, time, platform, shutil

PORT = 1111
_LIB = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_uv_local = os.path.expanduser('~/.local/bin/uv')
_UV = shutil.which('uv') or (_uv_local if os.access(_uv_local, os.X_OK) else None)
_WSL = os.path.exists('/proc/sys/fs/binfmt_misc/WSLInterop')

def _url(p): return f'http://localhost:{p}'

def _cmd(m, p):
    s = f'{_LIB}/ui/{m}.py'
    if _UV: return [_UV, 'run', '--script', s, str(p)]
    vp = os.path.join(os.path.dirname(_LIB), 'adata', 'venv', 'bin', 'python')
    py = vp if os.access(vp, os.X_OK) else sys.executable
    return [py, '-c', f"from ui.{m} import run;run({p})"]

def _open(url):
    if _WSL:
        S.Popen(['cmd.exe', '/c', 'start', url], stdout=S.DEVNULL, stderr=S.DEVNULL)
    else:
        import webbrowser; webbrowser.open(url)

def _bg(m, p):
    S.Popen(_cmd(m, p), start_new_session=True, stdout=S.DEVNULL, stderr=None, env={**os.environ, 'PYTHONPATH': _LIB})
    time.sleep(0.3); _open(_url(p))

_TERMUX = os.path.isdir('/data/data/com.termux')
def _plist(): return os.path.expanduser('~/Library/LaunchAgents/com.a.ui.plist')
def _unit(): return os.path.expanduser('~/.config/systemd/user/a-ui.service')
def _svdir(): return os.path.join(os.environ.get('PREFIX', '/usr'), 'var/service/a-ui')

def _svc_off():
    if platform.system() == 'Darwin':
        p = _plist()
        if os.path.exists(p): S.run(['launchctl', 'unload', p], capture_output=True); os.remove(p)
    elif _TERMUX:
        sd = _svdir()
        if os.path.isdir(sd): S.run(['sv', 'down', 'a-ui'], capture_output=True); S.run(['rm', '-rf', sd])
    else:
        S.run(['systemctl', '--user', 'disable', '--now', 'a-ui'], capture_output=True)
        u = _unit()
        if os.path.exists(u): os.remove(u)

def _svc_on(m='ui_full', p=PORT):
    rc = _cmd(m, p); cmd = ' '.join(rc)
    if platform.system() == 'Darwin':
        pf = _plist(); _svc_off()
        os.makedirs(os.path.dirname(pf), exist_ok=True)
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
        S.run(['launchctl', 'load', pf], capture_output=True); return True
    if _TERMUX:
        sd = _svdir(); _svc_off(); os.makedirs(sd, exist_ok=True); rs = os.path.join(sd, 'run')
        prefix = os.environ.get('PREFIX', '/data/data/com.termux/files/usr')
        with open(rs, 'w') as f: f.write(f'#!{prefix}/bin/sh\nexec {cmd}\n')
        os.chmod(rs, 0o755); S.run(['sv', 'up', 'a-ui'], capture_output=True); return True
    if S.run(['systemctl', '--user', '--version'], capture_output=True).returncode == 0:
        _svc_off(); ud = os.path.dirname(_unit()); os.makedirs(ud, exist_ok=True)
        with open(_unit(), 'w') as f:
            f.write(f'[Unit]\nDescription=a UI server\n[Service]\nExecStart={cmd}\nEnvironment=PYTHONPATH={_LIB}\nRestart=always\nRestartSec=2\n[Install]\nWantedBy=default.target\n')
        S.run(['systemctl', '--user', 'daemon-reload']); S.run(['systemctl', '--user', 'enable', '--now', 'a-ui']); return True
    return False

def run():
    a = sys.argv[2:]
    if a and a[0][0] == 'k':
        S.run(['pkill', '-9', '-f', 'ui.ui_']); print('Killed (service will restart)')
    elif a and a[0] == 'on':
        if _svc_on(): print(f'UI service on — {_url(PORT)}')
        else: print('No service manager (use a ui)'); sys.exit(1)
    elif a and a[0] == 'off':
        _svc_off(); S.run(['pkill', '-9', '-f', 'ui.ui_']); print('UI service off')
    else:
        p = int(a[0]) if a and a[0].isdigit() else PORT
        S.run(['pkill','-9','-f','ui.ui_'],capture_output=True)
        _bg('ui_full', p)
        print(f"{_url(p)}\n  on  auto-start service\n  off stop service\n  k   kill")

if __name__ == '__main__': run()
